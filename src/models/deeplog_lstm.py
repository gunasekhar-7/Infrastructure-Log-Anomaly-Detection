"""DeepLog Sequential PyTorch LSTM Next-Token Prediction Anomaly Detector."""

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config.logging import get_logger
from src.exceptions import ModelNotTrainedError
from src.models.base import BaseAnomalyDetector

logger = get_logger("deeplog_detector")


class DeepLogLSTMNet(nn.Module):
    """PyTorch Neural Network for modeling log template sequence transitions."""

    def __init__(
        self,
        vocab_size: int,
        embedding_dim: int = 32,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.vocab_size = vocab_size
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        self.lstm = nn.LSTM(
            input_size=embedding_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc = nn.Linear(hidden_size, vocab_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass predicting logits for next log template index."""
        # x: (batch_size, sequence_length)
        embeds = self.embedding(x)  # (batch_size, seq_len, embed_dim)
        lstm_out, _ = self.lstm(embeds)  # (batch_size, seq_len, hidden_size)
        last_hidden = lstm_out[:, -1, :]  # (batch_size, hidden_size)
        logits = self.fc(last_hidden)  # (batch_size, vocab_size)
        return logits


class DeepLogDetector(BaseAnomalyDetector):
    """DeepLog-inspired sequential next-event prediction anomaly detector.

    Learns normal execution sequence patterns by predicting the top-k candidate
    next events. Flags out-of-order execution, skipped steps, and broken paths.
    """

    def __init__(
        self,
        vocab_size: int = 50,
        top_k: int = 5,
        embedding_dim: int = 32,
        hidden_size: int = 64,
        num_layers: int = 2,
        lr: float = 0.005,
        batch_size: int = 64,
        epochs: int = 10,
        version: str = "v1.0",
        device: str | None = None,
    ) -> None:
        super().__init__(
            model_name="DeepLogSequentialDetector",
            algorithm="DEEPLOG_LSTM_NEXT_EVENT",
            version=version,
            threshold=0.5,
        )
        self.vocab_size = vocab_size
        self.top_k = top_k
        self.embedding_dim = embedding_dim
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.lr = lr
        self.batch_size = batch_size
        self.epochs = epochs

        # Select available execution device
        if device:
            self.device = torch.device(device)
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.net = DeepLogLSTMNet(
            vocab_size=vocab_size,
            embedding_dim=embedding_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
        ).to(self.device)

        self.hyperparameters = {
            "vocab_size": vocab_size,
            "top_k": top_k,
            "embedding_dim": embedding_dim,
            "hidden_size": hidden_size,
            "num_layers": num_layers,
            "lr": lr,
            "batch_size": batch_size,
            "epochs": epochs,
            "device": str(self.device),
        }

    def fit_sequences(
        self,
        X_seq: np.ndarray,
        y_seq: np.ndarray,
        val_data: tuple[np.ndarray, np.ndarray] | None = None,
    ) -> "DeepLogDetector":
        """Train DeepLog LSTM network on normal sequential (X, y) token transitions."""
        if len(X_seq) == 0:
            raise ValueError("Cannot train DeepLogDetector on empty sequence data.")

        # Ensure vocab_size is large enough for all token indices
        max_idx = max(int(np.max(X_seq)), int(np.max(y_seq)))
        if max_idx >= self.vocab_size:
            self.vocab_size = max_idx + 5
            self.net = DeepLogLSTMNet(
                vocab_size=self.vocab_size,
                embedding_dim=self.embedding_dim,
                hidden_size=self.hidden_size,
                num_layers=self.num_layers,
            ).to(self.device)

        tensor_X = torch.tensor(X_seq, dtype=torch.long)
        tensor_y = torch.tensor(y_seq, dtype=torch.long)

        dataset = TensorDataset(tensor_X, tensor_y)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(self.net.parameters(), lr=self.lr)

        self.net.train()
        logger.info(
            "Training DeepLogDetector (%s) on %d samples for %d epochs...",
            self.device,
            len(X_seq),
            self.epochs,
        )

        for epoch in range(1, self.epochs + 1):
            total_loss = 0.0
            for batch_X, batch_y in loader:
                batch_X = batch_X.to(self.device)
                batch_y = batch_y.to(self.device)

                optimizer.zero_grad()
                logits = self.net(batch_X)
                loss = criterion(logits, batch_y)
                loss.backward()
                optimizer.step()

                total_loss += loss.item() * batch_X.size(0)

            avg_loss = total_loss / len(X_seq)
            if epoch % 5 == 0 or epoch == self.epochs:
                logger.debug("DeepLog Epoch %d/%d - Loss: %.4f", epoch, self.epochs, avg_loss)

        self.is_fitted = True
        self.training_metadata = {
            "n_train_samples": len(X_seq),
            "final_epoch_loss": round(avg_loss, 4),
            "device": str(self.device),
        }
        return self

    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> "DeepLogDetector":
        """Compatibility fit method.

        If X has >= 2 columns, treats X[:, :-1] as input sequence and X[:, -1] as target.
        """
        if X.ndim == 2 and X.shape[1] > 1:
            X_seq = X[:, :-1].astype(np.int64)
            y_seq = X[:, -1].astype(np.int64)
            return self.fit_sequences(X_seq, y_seq)
        else:
            raise ValueError("DeepLog fit expects 2D sequence matrix with at least 2 columns.")

    def score_sequences(self, X_seq: np.ndarray, y_seq: np.ndarray) -> np.ndarray:
        """Compute anomaly score for each (sequence, next_event) pair.

        If actual event is in top-k candidate set: score = 0.0 (normal).
        If actual event is NOT in top-k: score = 1.0 - sum(P(top_k)) (anomaly confidence).
        """
        if not self.is_fitted:
            raise ModelNotTrainedError("DeepLogDetector is not fitted.")

        self.net.eval()
        scores = np.zeros(len(X_seq), dtype=np.float32)

        tensor_X = torch.tensor(X_seq, dtype=torch.long).to(self.device)
        dataset = TensorDataset(tensor_X)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=False)

        all_logits = []
        with torch.no_grad():
            for (batch_X,) in loader:
                logits = self.net(batch_X)
                all_logits.append(logits.cpu())

        all_logits = torch.cat(all_logits, dim=0)
        probs = torch.softmax(all_logits, dim=-1).numpy()

        k = min(self.top_k, self.vocab_size)

        for i in range(len(X_seq)):
            actual_y = int(y_seq[i])
            sample_probs = probs[i]

            # Get top-k indices with highest probability
            top_indices = np.argsort(sample_probs)[-k:]
            top_prob_sum = float(np.sum(sample_probs[top_indices]))

            if actual_y in top_indices:
                # Normal state transition
                scores[i] = 0.0
            else:
                # Anomalous out-of-order transition: confidence proportional to top-k certainty
                scores[i] = float(np.clip(1.0 - (1.0 - top_prob_sum) * 0.5, 0.5, 1.0))

        return scores

    def score(self, X: np.ndarray) -> np.ndarray:
        """Score input sequence matrix."""
        if X.ndim == 2 and X.shape[1] > 1:
            X_seq = X[:, :-1].astype(np.int64)
            y_seq = X[:, -1].astype(np.int64)
            return self.score_sequences(X_seq, y_seq)
        raise ValueError("DeepLog score expects 2D sequence matrix with at least 2 columns.")

    def save(self, artifact_path: Path | str) -> None:
        """Serialize PyTorch weights and model configuration."""
        if not self.is_fitted:
            raise ModelNotTrainedError("Cannot save unfitted DeepLogDetector.")

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
            "vocab_size": self.vocab_size,
            "top_k": self.top_k,
            "embedding_dim": self.embedding_dim,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "hyperparameters": self.hyperparameters,
            "training_metadata": self.training_metadata,
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        logger.info("Saved DeepLogDetector to %s and %s", model_file, meta_file)

    @classmethod
    def load(cls, artifact_path: Path | str) -> "DeepLogDetector":
        """Load trained DeepLog model from saved weights and metadata."""
        path = Path(artifact_path)
        meta_file = path.with_suffix(".json")
        model_file = path.with_suffix(".pt")

        with open(meta_file, encoding="utf-8") as f:
            meta = json.load(f)

        detector = cls(
            vocab_size=meta["vocab_size"],
            top_k=meta["top_k"],
            embedding_dim=meta["embedding_dim"],
            hidden_size=meta["hidden_size"],
            num_layers=meta["num_layers"],
            version=meta.get("version", "v1.0"),
        )
        detector.threshold = meta.get("threshold", 0.5)
        detector.net.load_state_dict(
            torch.load(model_file, map_location=detector.device)
        )
        detector.is_fitted = True
        detector.training_metadata = meta.get("training_metadata", {})
        return detector

