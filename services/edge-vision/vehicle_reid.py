"""
CitiSentry Vehicle Re-ID Engine (OSNet x1.0)
=============================================
Isolated, self-contained module implementing the OSNet architecture
(Omni-Scale Network) for vehicle re-identification.

OSNet learns multi-scale features (headlights, doors, taillights) and fuses
them through an Aggregation Gate, making it dramatically more robust than
generic CNNs for matching vehicles across different camera angles and scales.

Architecture is implemented in pure PyTorch (no torchreid dependency) for
maximum portability on Windows and Linux.

Weights: ImageNet-pretrained osnet_x1_0 from HuggingFace (kaiyangzhou/osnet).
Fallback: torchvision ResNet-18 if weight download fails.
"""

import os
import sys
import numpy as np
import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F
from collections import OrderedDict

# ══════════════════════════════════════════════════════════════════════════════
# OSNet Architecture (Self-Contained)
# ══════════════════════════════════════════════════════════════════════════════

class ConvLayer(nn.Module):
    """Standard conv + BN + ReLU block."""
    def __init__(self, in_channels, out_channels, kernel_size, stride=1, padding=0, groups=1, IN=False):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size, stride=stride, padding=padding, bias=False, groups=groups)
        if IN:
            self.bn = nn.InstanceNorm2d(out_channels, affine=True)
        else:
            self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        return self.relu(self.bn(self.conv(x)))


class Conv1x1(nn.Module):
    """1x1 conv + BN + optional ReLU."""
    def __init__(self, in_channels, out_channels, stride=1, groups=1):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, 1, stride=stride, padding=0, bias=False, groups=groups)
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        return self.relu(self.bn(self.conv(x)))


class Conv1x1Linear(nn.Module):
    """1x1 conv + BN (no ReLU)."""
    def __init__(self, in_channels, out_channels, stride=1):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, 1, stride=stride, padding=0, bias=False)
        self.bn = nn.BatchNorm2d(out_channels)

    def forward(self, x):
        return self.bn(self.conv(x))


class LightConv3x3(nn.Module):
    """Lightweight 3x3 depthwise separable convolution."""
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, in_channels, 1, stride=1, padding=0, bias=False)
        self.conv2 = nn.Conv2d(in_channels, out_channels, 3, stride=1, padding=1, bias=False, groups=in_channels)
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2(x)
        return self.relu(self.bn(x))


class ChannelGate(nn.Module):
    """Aggregation Gate for multi-scale feature fusion."""
    def __init__(self, in_channels, num_gates=None, return_gates=False, gate_activation='sigmoid', reduction=16):
        super().__init__()
        if num_gates is None:
            num_gates = in_channels
        self.return_gates = return_gates
        self.global_avgpool = nn.AdaptiveAvgPool2d(1)
        self.fc1 = nn.Conv2d(in_channels, in_channels // reduction, kernel_size=1, bias=True, padding=0)
        self.norm1 = None
        self.relu = nn.ReLU(inplace=True)
        self.fc2 = nn.Conv2d(in_channels // reduction, num_gates, kernel_size=1, bias=True, padding=0)
        if gate_activation == 'sigmoid':
            self.gate_activation = nn.Sigmoid()
        elif gate_activation == 'relu':
            self.gate_activation = nn.ReLU(inplace=True)
        elif gate_activation == 'linear':
            self.gate_activation = None
        else:
            raise RuntimeError(f"Unknown gate activation: {gate_activation}")

    def forward(self, x):
        inp = x
        x = self.global_avgpool(x)
        x = self.fc1(x)
        if self.norm1 is not None:
            x = self.norm1(x)
        x = self.relu(x)
        x = self.fc2(x)
        if self.gate_activation is not None:
            x = self.gate_activation(x)
        if self.return_gates:
            return x
        return inp * x


class OSBlock(nn.Module):
    """Omni-Scale feature learning block."""
    def __init__(self, in_channels, out_channels, IN=False, bottleneck_reduction=4, **kwargs):
        super().__init__()
        mid_channels = out_channels // bottleneck_reduction
        self.conv1 = Conv1x1(in_channels, mid_channels)
        self.conv2a = LightConv3x3(mid_channels, mid_channels)
        self.conv2b = nn.Sequential(
            LightConv3x3(mid_channels, mid_channels),
            LightConv3x3(mid_channels, mid_channels),
        )
        self.conv2c = nn.Sequential(
            LightConv3x3(mid_channels, mid_channels),
            LightConv3x3(mid_channels, mid_channels),
            LightConv3x3(mid_channels, mid_channels),
        )
        self.conv2d = nn.Sequential(
            LightConv3x3(mid_channels, mid_channels),
            LightConv3x3(mid_channels, mid_channels),
            LightConv3x3(mid_channels, mid_channels),
            LightConv3x3(mid_channels, mid_channels),
        )
        self.gate = ChannelGate(mid_channels)
        self.conv3 = Conv1x1Linear(mid_channels, out_channels)
        self.downsample = None
        if in_channels != out_channels:
            self.downsample = Conv1x1Linear(in_channels, out_channels)
        self.IN = None
        if IN:
            self.IN = nn.InstanceNorm2d(out_channels, affine=True)

    def forward(self, x):
        identity = x
        x1 = self.conv1(x)
        x2a = self.conv2a(x1)
        x2b = self.conv2b(x1)
        x2c = self.conv2c(x1)
        x2d = self.conv2d(x1)
        x2 = self.gate(x2a) + self.gate(x2b) + self.gate(x2c) + self.gate(x2d)
        x3 = self.conv3(x2)
        if self.downsample is not None:
            identity = self.downsample(identity)
        out = x3 + identity
        if self.IN is not None:
            out = self.IN(out)
        return F.relu(out)


class OSNet(nn.Module):
    """Omni-Scale Network (osnet_x1_0)."""
    def __init__(self, num_classes, blocks, layers, channels, feature_dim=512, IN=False, **kwargs):
        super().__init__()
        num_blocks = len(blocks)
        assert num_blocks == len(layers)
        assert num_blocks == len(channels) - 1

        # convolutional backbone
        self.conv1 = ConvLayer(3, channels[0], 7, stride=2, padding=3, IN=IN)
        self.maxpool = nn.MaxPool2d(3, stride=2, padding=1)
        self.conv2 = self._make_layer(blocks[0], layers[0], channels[0], channels[1], reduce_spatial_size=True, IN=IN)
        self.conv3 = self._make_layer(blocks[1], layers[1], channels[1], channels[2], reduce_spatial_size=True)
        self.conv4 = self._make_layer(blocks[2], layers[2], channels[2], channels[3], reduce_spatial_size=False)
        self.conv5 = Conv1x1(channels[3], channels[3])
        self.global_avgpool = nn.AdaptiveAvgPool2d(1)
        # fully connected layer
        self.fc = self._construct_fc_layer(feature_dim, channels[3], dropout_p=None)
        # identity classification layer
        self.classifier = nn.Linear(feature_dim, num_classes)

        self._init_params()

    def _make_layer(self, block, layer, in_channels, out_channels, reduce_spatial_size, IN=False):
        layers_list = []
        layers_list.append(block(in_channels, out_channels, IN=IN))
        for _ in range(1, layer):
            layers_list.append(block(out_channels, out_channels, IN=IN))
        if reduce_spatial_size:
            layers_list.append(
                nn.Sequential(
                    Conv1x1(out_channels, out_channels),
                    nn.AvgPool2d(2, stride=2)
                )
            )
        return nn.Sequential(*layers_list)

    def _construct_fc_layer(self, fc_dims, input_dim, dropout_p=None):
        if fc_dims is None or fc_dims < 0:
            self.feature_dim = input_dim
            return None
        if isinstance(fc_dims, int):
            fc_dims = [fc_dims]
        layers = []
        for dim in fc_dims:
            layers.append(nn.Linear(input_dim, dim))
            layers.append(nn.BatchNorm1d(dim))
            layers.append(nn.ReLU(inplace=True))
            if dropout_p is not None:
                layers.append(nn.Dropout(p=dropout_p))
            input_dim = dim
        self.feature_dim = fc_dims[-1]
        return nn.Sequential(*layers)

    def _init_params(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm1d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                nn.init.normal_(m.weight, 0, 0.01)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def featuremaps(self, x):
        x = self.conv1(x)
        x = self.maxpool(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.conv4(x)
        x = self.conv5(x)
        return x

    def forward(self, x, return_featuremaps=False):
        x = self.featuremaps(x)
        if return_featuremaps:
            return x
        v = self.global_avgpool(x)
        v = v.view(v.size(0), -1)
        if self.fc is not None:
            v = self.fc(v)
        if not self.training:
            return v
        y = self.classifier(v)
        return y


def _osnet_x1_0(num_classes=1000, pretrained=False, **kwargs):
    model = OSNet(
        num_classes,
        blocks=[OSBlock, OSBlock, OSBlock],
        layers=[2, 2, 2],
        channels=[64, 256, 384, 512],
        **kwargs
    )
    return model


# ══════════════════════════════════════════════════════════════════════════════
# Vehicle Re-ID Engine Class
# ══════════════════════════════════════════════════════════════════════════════

OSNET_WEIGHTS_URL = "https://huggingface.co/kaiyangzhou/osnet/resolve/main/osnet_x1_0_imagenet.pth"
WEIGHTS_FILENAME = "osnet_x1_0_imagenet.pth"


class VehicleReIDEngine:
    """
    Isolated, self-contained Vehicle Re-Identification engine.
    
    Uses OSNet x1.0 (Omni-Scale Network) pre-trained on ImageNet.
    Falls back to ResNet-18 if the OSNet weights cannot be downloaded.
    """

    def __init__(self, weights_dir: str | None = None):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = None
        self.feature_dim = 512  # OSNet x1.0 outputs 512-d vectors
        self.using_fallback = False

        if weights_dir is None:
            weights_dir = os.path.dirname(os.path.abspath(__file__))

        weights_path = os.path.join(weights_dir, WEIGHTS_FILENAME)

        # ── Try OSNet ────────────────────────────────────────────────────
        try:
            if not os.path.exists(weights_path):
                print(f"[Re-ID] Downloading OSNet weights to {weights_path}...")
                self._download_weights(OSNET_WEIGHTS_URL, weights_path)

            model = _osnet_x1_0(num_classes=1000, pretrained=False)
            state_dict = torch.load(weights_path, map_location=self.device, weights_only=True)
            model.load_state_dict(state_dict)
            # Remove the classifier head so forward() returns the 512-d feature vector
            model.classifier = nn.Identity()
            model = model.to(self.device)
            model.eval()
            self.model = model
            print(f"[Re-ID] OSNet x1.0 loaded successfully on {self.device} (512-d embeddings)")

        except Exception as e:
            print(f"[Re-ID] OSNet load failed: {e}", file=sys.stderr)
            print("[Re-ID] Falling back to ResNet-18 (ImageNet)...", file=sys.stderr)
            self._init_fallback()

    def _init_fallback(self):
        """Initialize a ResNet-18 fallback if OSNet fails."""
        try:
            import torchvision.models as models
            model = models.resnet18(weights='DEFAULT')
            self.feature_dim = model.fc.in_features  # 512
            model.fc = nn.Identity()
            model = model.to(self.device)
            model.eval()
            self.model = model
            self.using_fallback = True
            print(f"[Re-ID] ResNet-18 fallback loaded on {self.device} ({self.feature_dim}-d embeddings)")
        except Exception as e2:
            print(f"[Re-ID] CRITICAL: Fallback also failed: {e2}", file=sys.stderr)
            self.model = None

    @staticmethod
    def _download_weights(url: str, dest: str):
        """Download weights using urllib (no extra dependencies)."""
        import urllib.request
        os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        file_size = os.path.getsize(dest)
        print(f"[Re-ID] Downloaded {file_size / 1024 / 1024:.1f} MB")

    def extract_embedding(self, cv2_image_crop: np.ndarray) -> np.ndarray | None:
        """
        Extract a normalized feature vector from an OpenCV BGR image crop.
        
        Args:
            cv2_image_crop: BGR image crop (any size, will be resized to 256x128).
            
        Returns:
            L2-normalized 1-D numpy array of shape (feature_dim,), or None on failure.
        """
        if self.model is None:
            return None

        try:
            if cv2_image_crop.size == 0 or cv2_image_crop.shape[0] < 4 or cv2_image_crop.shape[1] < 4:
                return None

            # Convert BGR -> RGB, resize to 256x128 (standard ReID input: H x W)
            crop_rgb = cv2.cvtColor(cv2_image_crop, cv2.COLOR_BGR2RGB)
            crop_resized = cv2.resize(crop_rgb, (128, 256), interpolation=cv2.INTER_LINEAR)

            # Normalize to ImageNet statistics
            img = crop_resized.astype(np.float32) / 255.0
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            img = (img - mean) / std

            # HWC -> CHW -> NCHW
            tensor = torch.from_numpy(img.transpose(2, 0, 1)).unsqueeze(0).to(self.device)

            with torch.no_grad():
                embedding = self.model(tensor)
                # L2 normalize
                embedding = F.normalize(embedding, p=2, dim=1)
                return embedding.cpu().numpy().flatten()

        except Exception as e:
            print(f"[Re-ID] Embedding extraction failed: {e}", file=sys.stderr)
            return None

    @staticmethod
    def compute_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Compute cosine similarity between two L2-normalized embeddings.
        
        Returns:
            Float in [-1.0, 1.0]. Values > 0.75 indicate a strong match.
        """
        if emb1 is None or emb2 is None:
            return -1.0
        dot = np.dot(emb1, emb2)
        return float(np.clip(dot, -1.0, 1.0))
