"""Sparse autoencoder for tactical residual-stream feature extraction."""

from __future__ import annotations

import logging
import os
from typing import Dict

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

logger = logging.getLogger(__name__)


class SparseAutoencoder(nn.Module):
    """Single-layer sparse autoencoder for white-box feature analysis.

    The decoder matrix maps latent features back into residual space. Each
    decoder matrix column is a tactical steering direction for the matching SAE
    feature index.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 16384,
        sparsity_coefficient: float = 1e-3,
    ) -> None:
        """Initialize SAE layers and place model on CUDA when available."""
        super().__init__()
        if input_dim <= 0:
            raise ValueError("input_dim must be > 0")
        if hidden_dim <= 0:
            raise ValueError("hidden_dim must be > 0")
        if sparsity_coefficient < 0:
            raise ValueError("sparsity_coefficient must be >= 0")

        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.sparsity_coefficient = float(sparsity_coefficient)

        self.encoder = nn.Linear(self.input_dim, self.hidden_dim)
        self.activation = nn.ReLU()
        self.decoder = nn.Linear(self.hidden_dim, self.input_dim)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.to(self.device)
        logger.info(
            "Initialized SparseAutoencoder(input_dim=%s, hidden_dim=%s) on %s",
            self.input_dim,
            self.hidden_dim,
            self.device,
        )

    def _ensure_2d(self, activations: torch.Tensor) -> tuple[torch.Tensor, bool]:
        """Normalize activations to shape [batch, input_dim] on model device."""
        if activations.ndim == 1:
            if activations.shape[0] != self.input_dim:
                raise ValueError(
                    f"1D activations length mismatch: expected {self.input_dim}, got {activations.shape[0]}"
                )
            return activations.unsqueeze(0).to(self.device), True

        if activations.ndim == 2:
            if activations.shape[1] != self.input_dim:
                raise ValueError(
                    f"2D activations width mismatch: expected {self.input_dim}, got {activations.shape[1]}"
                )
            return activations.to(self.device), False

        if activations.ndim == 3 and activations.shape[-1] == self.input_dim:
            flattened = activations.reshape(-1, self.input_dim)
            return flattened.to(self.device), False

        raise ValueError(
            "activations must have shape [input_dim], [batch, input_dim], "
            "or [batch, seq, input_dim]"
        )

    def encode(self, activations: torch.Tensor) -> torch.Tensor:
        """Encode residual activations into sparse latent features."""
        logger.debug("Encoding activations with shape=%s", tuple(activations.shape))
        normalized, was_vector = self._ensure_2d(activations)
        features = self.activation(self.encoder(normalized))
        return features.squeeze(0) if was_vector else features

    def decode(self, features: torch.Tensor) -> torch.Tensor:
        """Decode latent SAE features back to residual-stream activations."""
        logger.debug("Decoding features with shape=%s", tuple(features.shape))
        was_vector = False
        if features.ndim == 1:
            if features.shape[0] != self.hidden_dim:
                raise ValueError(
                    f"1D feature length mismatch: expected {self.hidden_dim}, got {features.shape[0]}"
                )
            features = features.unsqueeze(0)
            was_vector = True
        elif features.ndim != 2 or features.shape[1] != self.hidden_dim:
            raise ValueError(
                f"features must have shape [hidden_dim] or [batch, hidden_dim], got {tuple(features.shape)}"
            )
        reconstruction = self.decoder(features.to(self.device))
        return reconstruction.squeeze(0) if was_vector else reconstruction

    def reconstruction_loss(
        self,
        activations: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Compute SAE reconstruction loss and sparse activations."""
        normalized, _ = self._ensure_2d(activations)
        features = self.activation(self.encoder(normalized))
        reconstructions = self.decoder(features)
        recon_loss = nn.functional.mse_loss(reconstructions, normalized)
        sparsity_penalty = features.abs().mean()
        total = recon_loss + self.sparsity_coefficient * sparsity_penalty
        logger.debug(
            "Computed losses recon=%.6f sparsity=%.6f total=%.6f",
            float(recon_loss.detach().cpu()),
            float(sparsity_penalty.detach().cpu()),
            float(total.detach().cpu()),
        )
        return total, recon_loss, sparsity_penalty

    def get_feature_direction(self, feature_index: int) -> torch.Tensor:
        """Return one decoder column used for activation steering."""
        if feature_index < 0 or feature_index >= self.hidden_dim:
            raise ValueError(
                f"feature_index must be in [0, {self.hidden_dim - 1}], got {feature_index}"
            )
        direction = self.decoder.weight[:, feature_index].detach()
        logger.debug(
            "Retrieved steering direction for feature_index=%s with norm=%.6f",
            feature_index,
            float(direction.norm().cpu()),
        )
        return direction

    def get_active_features(
        self,
        activations: torch.Tensor,
        threshold: float = 0.01,
    ) -> Dict[int, float]:
        """Return active latent features above threshold from input activations."""
        if threshold < 0:
            raise ValueError("threshold must be >= 0")
        feature_tensor = self.encode(activations)
        if feature_tensor.ndim == 1:
            aggregate = feature_tensor
        else:
            aggregate = feature_tensor.mean(dim=0)

        active_indices = torch.nonzero(aggregate > threshold, as_tuple=False).flatten()
        active_map = {
            int(index.item()): float(aggregate[index].detach().cpu().item())
            for index in active_indices
        }
        logger.debug(
            "Detected %s active features above threshold %.5f",
            len(active_map),
            threshold,
        )
        return active_map

    def train_on_dataset(
        self,
        dataset: torch.Tensor,
        epochs: int = 100,
        batch_size: int = 256,
        lr: float = 1e-4,
    ) -> None:
        """Train SAE on residual-stream activation data."""
        if epochs <= 0:
            raise ValueError("epochs must be > 0")
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if lr <= 0:
            raise ValueError("lr must be > 0")

        activations = dataset.detach().float()
        if activations.ndim == 1:
            activations = activations.unsqueeze(0)
        if activations.ndim == 3 and activations.shape[-1] == self.input_dim:
            activations = activations.reshape(-1, self.input_dim)
        elif activations.ndim != 2 or activations.shape[1] != self.input_dim:
            raise ValueError(
                "dataset must have shape [n, input_dim] or [n, seq, input_dim]"
            )

        loader = DataLoader(
            TensorDataset(activations.cpu()),
            batch_size=batch_size,
            shuffle=True,
            drop_last=False,
            pin_memory=torch.cuda.is_available(),
        )
        optimizer = torch.optim.Adam(self.parameters(), lr=lr)
        self.train()
        logger.info(
            "Starting SAE training: samples=%s epochs=%s batch_size=%s lr=%s device=%s",
            activations.shape[0],
            epochs,
            batch_size,
            lr,
            self.device,
        )

        log_every = max(1, epochs // 10)
        for epoch in range(epochs):
            epoch_loss = 0.0
            for (batch,) in loader:
                batch = batch.to(self.device, non_blocking=True)
                optimizer.zero_grad(set_to_none=True)
                total_loss, _, _ = self.reconstruction_loss(batch)
                total_loss.backward()
                optimizer.step()
                epoch_loss += float(total_loss.detach().cpu())

            if (epoch + 1) % log_every == 0 or epoch == 0:
                avg_loss = epoch_loss / max(1, len(loader))
                logger.info("SAE epoch %s/%s average_loss=%.6f", epoch + 1, epochs, avg_loss)

    def save(self, path: str) -> None:
        """Persist SAE parameters and architecture metadata to disk."""
        logger.info("Saving SparseAutoencoder to %s", path)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "sparsity_coefficient": self.sparsity_coefficient,
            "state_dict": self.state_dict(),
        }
        torch.save(payload, path)

    @classmethod
    def load(cls, path: str) -> "SparseAutoencoder":
        """Load a persisted SAE checkpoint from disk."""
        logger.info("Loading SparseAutoencoder from %s", path)
        payload = torch.load(path, map_location="cpu")
        required_keys = {"input_dim", "hidden_dim", "sparsity_coefficient", "state_dict"}
        if not required_keys.issubset(payload):
            missing = required_keys.difference(payload)
            raise ValueError(f"SAE checkpoint missing keys: {sorted(missing)}")

        sae = cls(
            input_dim=int(payload["input_dim"]),
            hidden_dim=int(payload["hidden_dim"]),
            sparsity_coefficient=float(payload["sparsity_coefficient"]),
        )
        sae.load_state_dict(payload["state_dict"])
        sae.eval()
        return sae
