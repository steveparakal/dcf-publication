"""
forecasting/dl_models.py

LSTM, GRU, and Temporal Convolutional Network (TCN) forecasting model
adapters (DCF specification, "Deep Learning Models").

Backend: PyTorch, frozen per DCF design.

Each model is windowed-sequence-to-one: given input_window past
observations, predict the next single value. Multi-step forecasting uses
the same RECURSIVE strategy as the ML models (forecasting/ml_models.py)
for the same reason -- no alternative multi-step strategy is specified
anywhere in the framework documents, so recursive single-step prediction
is the implementation default, flagged explicitly in the v1.2.0 report.

Reproducibility: the global random seed is applied to torch's RNG before
every training run, with deterministic algorithm flags set per the
frozen config.

Early stopping uses a simple held-out tail of the training window itself
(not a separate validation set), since the framework's data-preparation
layer does not define a train/val/test three-way split -- only the
train/test rolling-origin split. Flagged explicitly as an implementation
choice filling a gap the framework documents leave open.
"""



from __future__ import annotations



import numpy as np

import pandas as pd



try:

    import torch

    import torch.nn as nn

    _TORCH_AVAILABLE = True

except Exception:

    torch = None  

    nn = None     

    _TORCH_AVAILABLE = False



from dcf.config import get_config

from dcf.forecasting.exception_context import ExternalDependencyError, _raise_if_external_api_error





def _set_seed(seed):

    torch.manual_seed(seed)

    if torch.cuda.is_available():

        torch.cuda.manual_seed_all(seed)





def _make_sequences(values, input_window):

    n = len(values)

    if n <= input_window:

        return np.empty((0, input_window)), np.empty((0,))

    X = np.array([values[i:i + input_window] for i in range(n - input_window)], dtype=np.float32)

    y = np.array([values[i + input_window] for i in range(n - input_window)], dtype=np.float32)

    return X, y





class _RecurrentForecaster(nn.Module if _TORCH_AVAILABLE else object):

    def __init__(self, cell_type, hidden_size, num_layers, dropout):

        super().__init__()

        rnn_cls = nn.LSTM if cell_type == "lstm" else nn.GRU

        self.rnn = rnn_cls(

            input_size=1, hidden_size=hidden_size, num_layers=num_layers,

            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,

        )

        self.head = nn.Linear(hidden_size, 1)



    def forward(self, x):

        out, _ = self.rnn(x)

        last_step = out[:, -1, :]

        return self.head(last_step).squeeze(-1)





class _TCNBlock(nn.Module if _TORCH_AVAILABLE else object):

    def __init__(self, in_channels, out_channels, kernel_size, dilation, dropout):

        super().__init__()

        padding = (kernel_size - 1) * dilation

        self.conv = nn.Conv1d(in_channels, out_channels, kernel_size, padding=padding, dilation=dilation)

        self.relu = nn.ReLU()

        self.dropout = nn.Dropout(dropout)

        self.padding = padding



    def forward(self, x):

        out = self.conv(x)

        if self.padding > 0:

            out = out[:, :, :-self.padding]

        return self.dropout(self.relu(out))





class _TCNForecaster(nn.Module if _TORCH_AVAILABLE else object):

    def __init__(self, num_channels, kernel_size, dropout):

        super().__init__()

        layers = []

        in_ch = 1

        for i, out_ch in enumerate(num_channels):

            layers.append(_TCNBlock(in_ch, out_ch, kernel_size, dilation=2 ** i, dropout=dropout))

            in_ch = out_ch

        self.net = nn.Sequential(*layers)

        self.head = nn.Linear(in_ch, 1)



    def forward(self, x):

        x = x.transpose(1, 2)

        out = self.net(x)

        last_step = out[:, :, -1]

        return self.head(last_step).squeeze(-1)





def _train_and_predict(model, X, y, input_window, horizon, history,

                        learning_rate, batch_size, max_epochs, early_stopping_patience):

    X_t = torch.tensor(X).unsqueeze(-1)

    y_t = torch.tensor(y)



    n = len(X_t)

    val_size = max(1, int(0.1 * n)) if n >= 10 else 0

    if val_size > 0:

        X_train, y_train = X_t[:-val_size], y_t[:-val_size]

        X_val, y_val = X_t[-val_size:], y_t[-val_size:]

    else:

        X_train, y_train = X_t, y_t

        X_val, y_val = X_t, y_t



    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    loss_fn = nn.MSELoss()



    best_val_loss = float("inf")

    best_state = None

    patience_counter = 0



    for epoch in range(max_epochs):

        model.train()

        permutation = torch.randperm(len(X_train))

        for start in range(0, len(X_train), batch_size):

            idx = permutation[start:start + batch_size]

            optimizer.zero_grad()

            pred = model(X_train[idx])

            loss = loss_fn(pred, y_train[idx])

            loss.backward()

            optimizer.step()



        model.eval()

        with torch.no_grad():

            val_pred = model(X_val)

            val_loss = loss_fn(val_pred, y_val).item()



        if val_loss < best_val_loss - 1e-6:

            best_val_loss = val_loss

            best_state = {k: v.clone() for k, v in model.state_dict().items()}

            patience_counter = 0

        else:

            patience_counter += 1

            if patience_counter >= early_stopping_patience:

                break



    if best_state is not None:

        model.load_state_dict(best_state)



    model.eval()

    working_history = list(history[-input_window:])

    predictions = []

    with torch.no_grad():

        for _ in range(horizon):

            window = torch.tensor(np.array(working_history[-input_window:], dtype=np.float32)).reshape(1, input_window, 1)

            pred = model(window).item()

            predictions.append(pred)

            working_history.append(pred)



    return np.array(predictions, dtype=float)





def make_lstm_adapter(config=None):

    return _make_recurrent_adapter("lstm", config=config)





def make_gru_adapter(config=None):

    return _make_recurrent_adapter("gru", config=config)





def _make_recurrent_adapter(cell_type, config=None):

    cfg = config or get_config(allow_draft=False)

    params = cfg.get(f"forecasting.models.{cell_type}", {})

    seed = cfg.get("reproducibility.global_random_seed", 42)

    deterministic = cfg.get("reproducibility.torch_deterministic_algorithms", True)



    input_window = params.get("input_window", 24)

    hidden_size = params.get("hidden_size", 64)

    num_layers = params.get("num_layers", 2)

    dropout = params.get("dropout", 0.2)

    learning_rate = params.get("learning_rate", 0.001)

    batch_size = params.get("batch_size", 32)

    max_epochs = params.get("max_epochs", 100)

    patience = params.get("early_stopping_patience", 10)



    def _fit_predict(train, horizon):

        if deterministic:

            torch.use_deterministic_algorithms(True, warn_only=True)

        _set_seed(seed)



        values = train.to_numpy().astype(np.float32)

        if len(values) <= input_window:

            raise ValueError(

                f"{cell_type.upper()}: training window (n={len(values)}) must exceed "

                f"input_window ({input_window})."

            )



        X, y = _make_sequences(values, input_window)

        model = _RecurrentForecaster(cell_type, hidden_size, num_layers, dropout)



        return _train_and_predict(

            model, X, y, input_window, horizon, values,

            learning_rate, batch_size, max_epochs, patience,

        )



    return _fit_predict





def make_tcn_adapter(config=None):

    cfg = config or get_config(allow_draft=False)

    params = cfg.get("forecasting.models.tcn", {})

    seed = cfg.get("reproducibility.global_random_seed", 42)

    deterministic = cfg.get("reproducibility.torch_deterministic_algorithms", True)



    input_window = params.get("input_window", 24)

    num_channels = params.get("num_channels", [32, 32, 32, 32])

    kernel_size = params.get("kernel_size", 3)

    dropout = params.get("dropout", 0.2)

    learning_rate = params.get("learning_rate", 0.001)

    batch_size = params.get("batch_size", 32)

    max_epochs = params.get("max_epochs", 100)

    patience = params.get("early_stopping_patience", 10)



    def _fit_predict(train, horizon):

        if deterministic:

            torch.use_deterministic_algorithms(True, warn_only=True)

        _set_seed(seed)



        values = train.to_numpy().astype(np.float32)

        if len(values) <= input_window:

            raise ValueError(

                f"TCN: training window (n={len(values)}) must exceed "

                f"input_window ({input_window})."

            )



        X, y = _make_sequences(values, input_window)

        model = _TCNForecaster(num_channels, kernel_size, dropout)



        return _train_and_predict(

            model, X, y, input_window, horizon, values,

            learning_rate, batch_size, max_epochs, patience,

        )



    return _fit_predict





__all__ = ["make_lstm_adapter", "make_gru_adapter", "make_tcn_adapter"]

