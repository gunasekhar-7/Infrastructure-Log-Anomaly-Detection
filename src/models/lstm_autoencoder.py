"""LSTM Autoencoder Sequence Reconstruction Anomaly Detector."""

import json
from pathlib import Path
from typing import Any
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config.logging import get_logger
from src.exceptions import ModelNotTrainedError
from src.models.base import BaseAnomalyDetector

logger = get_logger("lstm_autoencoder")


class LSTMAutoencoderNet(nn.Module):
    """Sequence-to-Sequence LSTM Autoencoder for time-series reconstruction."""

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 32,
        latent_dim: int = 16,
        num_layers: int = 1,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim

        # Encoder
        self.encoder = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
        )
        self.enc_fc = nn.Linear(hidden_dim, latent_dim)

        # Decoder
        self.dec_fc = nn.Linear(latent_dim, hidden_dim)
        self.decoder = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
        )
        self.output_fc = nn.Linear(hidden_dim, input_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Encode sequence to latent representation and reconstruct original sequence."""
        # x: (batch, seq_len, input_dim)
        seq_len = x.size(1)
        enc_out, _ = self.encoder(x)
        last_hidden = enc_out[:, -1, :]
        latent = self.enc_fc(last_hidden)  # (batch, latent_dim)

        # Repeat latent vector across sequence length for decoding
        dec_init = self.dec_fc(latent).unsqueeze(1).repeat(1, seq_len, 1)  # (batch, seq_len, hidden)
        dec_out, _ = self.decoder(dec_init)
        reconstructed = self.output_fc(dec_out)  # (batch, seq_len, input_dim)
        return reconstructed


class LSTMAutoencoderDetector(BaseAnomalyDetector):
    """Reconstruction-based sequence anomaly detector using LSTM Autoencoder."""

    def __init__(
        self,
        input_dim: int = 1,
        hidden_dim: int = 32,
        latent_dim: int = 16,
        num_layers: int = 1,
        lr: float = 0.005,
        batch_size: int = 32,
        epochs: int = 10,
        version: str = "v1.0",
        device: str | None = None,
    ) -> None:
        super().__init__(
            model_name="LSTMAutoencoderDetector",
            algorithm="LSTM_AUTOENCODER_RECONSTRUCTION",
            version=version,
            threshold=0.5,
        )
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.num_layers = num_layers
        self.lr = lr
        self.batch_size = batch_size
        self.epochs = epochs

        self.device = torch.device(device) if device else torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.net = LSTMAutoencoderNet(
            input_dim=input_dim,
            hidden_dim=hidden_dim,
            latent_dim=latent_dim,
            num_layers=num_layers,
        ).to(self.device)

        self.max_baseline_mse_: float = 1.0
        self.hyperparameters = {
            "input_dim": input_dim,
            "hidden_dim": hidden_dim,
            "latent_dim": latent_dim,
            "lr": lr,
            "batch_size": batch_size,
            "epochs": epochs,
            "device": str(self.device),
        }

    def _prepare_tensor(self, X: np.ndarray) -> torch.Tensor:
        """Format 2D or 3D numpy arrays into (batch, seq_len, input_dim) tensor."""
        if X.ndim == 2:
            # (batch, seq_len) -> (batch, seq_len, 1)
            X = np.expand_dims(X, axis=-1)
        return torch.tensor(X, dtype=torch.float32)

    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> "LSTMAutoencoderDetector":
        """Train Autoencoder on normal baseline sequences."""
        if X.ndim == 2 and X.shape[-1] != self.input_dim and self.input_dim == 1:
            # Multi-feature window matrix
            pass
        elif X.ndim == 3 and X.shape[-1] != self.input_dim:
            self.input_dim = X.shape[-1]
            self.net = LSTMAutoencoderNet(
                input_dim=self.input_dim,
                hidden_dim=self.hidden_dim,
                latent_dim=self.latent_dim,
            ).to(self.device)

        tensor_X = self._prepare_tensor(X)
        dataset = TensorDataset(tensor_X)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(self.net.parameters(), lr=self.lr)

        self.net.train()
        logger.info(
            "Training LSTMAutoencoder (%s) on %d sequences for %d epochs...",
            self.device,
            len(X),
            self.epochs,
        )

        for epoch in range(1, self.epochs + 1):
            total_loss = 0.0
            for (batch_X,) in loader:
                batch_X = batch_X.to(self.device)
                optimizer.zero_grad()
                reconstructed = self.net(batch_X)
                loss = criterion(reconstructed, batch_X)
                loss.backward()
                optimizer.step()
                total_loss += loss.item() * batch_X.size(0)

        # Baseline reconstruction calibration
        self.net.eval()
        with torch.no_grad():
            reconstructed_baseline = self.net(tensor_X.to(self.device))
            mse_per_sample = torch.mean(
                (tensor_X.to(self.device) - reconstructed_baseline) ** 2, dim=(1, 2)
            ).cpu().numpy()
            self.max_baseline_mse_ = float(np.percentile(mse_per_sample, 98)) + 1e-5

        self.is_fitted = True
        self.training_metadata = {
            "n_train_samples": len(X),
            "max_baseline_mse": self.max_baseline_mse_,
        }
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        """Compute normalized reconstruction error in [0.0, 1.0]."""
        if not self.is_fitted:
            raise ModelNotTrainedError("LSTMAutoencoderDetector is not fitted.")

        tensor_X = self._prepare_tensor(X).to(self.device)
        self.net.eval()

        with torch.no_grad():
            reconstructed = self.net(tensor_X)
            mse = torch.mean((tensor_X - reconstructed) ** 2, dim=(1, 2)).cpu().numpy()

        # Normalize score into [0.0, 1.0] using baseline 98th percentile
        scores = mse / self.max_baseline_mse_
        return np.clip(scores, 0.0, 1.0)

    def save(self, artifact_path: Path | str) -> None:
        """Save PyTorch weights and metadata."""
        if not self.is_fitted:
            raise ModelNotTrainedError("Cannot save unfitted LSTMAutoencoder.")

        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        model_file = path.with_suffix(".pt")
        meta_file = path.with_suffix(".json")

        torch.save(self.net.state_dict(), model_file)
        meta = {
            "model_name": self.model_name,
            "algorithm": self.algorithm,
            "version": self.version,
            "threshold": self.threshold,
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "latent_dim": self.latent_dim,
            "max_baseline_mse": self.max_baseline_mse_,
            "hyperparameters": self.hyperparameters,
            "training_metadata": self.training_metadata,
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    @classmethod
    def load(cls, artifact_path: Path | str) -> "LSTMAutoencoderDetector":
        """Load trained autoencoder from disk."""
        path = Path(artifact_path)
        meta_file = path.with_suffix(".json")
        model_file = path.with_suffix(".pt")

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        detector = cls(
            input_dim=meta["input_dim"],
            hidden_dim=meta["hidden_dim"],
            latent_dim=meta["latent_dim"],
            version=meta.get("version", "v1.0"),
        )
        detector.threshold = meta.get("threshold", 0.5)
        detector.max_baseline_mse_ = meta.get("max_baseline_mse", 1.0)
        detector.net.load_state_dict(
            torch.load(model_file, map_location=detector.device)
        )
        detector.is_fitted = True
        return detector

