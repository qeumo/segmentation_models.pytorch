from typing import Optional, Union, List
from .decoder import EfficientUnetPlusPlusDecoder
from ..encoders import get_encoder
from ..base import SegmentationModel
from ..base import SegmentationHead, ClassificationHead
from torchvision import transforms

class EfficientUnetPlusPlus(SegmentationModel):
    """EfficientUnetPlusPlus_ is a fully convolution neural network for image semantic segmentation. Consist of *encoder* 
    and *decoder* parts connected with *skip connections*. The encoder extracts features of different spatial 
    resolution (skip connections) which are used by decoder to define accurate segmentation mask. 
    
    Applies attention to the skip connection feature maps, based on themselves and the decoder feature maps. 
    The skip connection feature maps are then fused with the decoder feature maps through *concatenation*. 
    Uses an Atrous Spatial Pyramid Pooling (ASPP) bridge module and residual connections inside each decoder 
    blocks.

    Args:
        encoder_name: Name of the classification model that will be used as an encoder (a.k.a backbone) to extract features
        encoder_depth: Number of stages of the encoder, in range [3 ,5]. Each stage generate features two times smaller, 
            in spatial dimensions, than the previous one (e.g., for depth=0 features will haves shapes [(N, C, H, W)]), 
            for depth 1 features will have shapes [(N, C, H, W), (N, C, H // 2, W // 2)] and so on).
            Default is 5
        encoder_weights: One of **None** (random initialization), **"imagenet"** (pre-training on ImageNet) and 
            other pretrained weights (see table with available weights for each encoder_name)
        decoder_channels: List of integers which specify **in_channels** parameter for convolutions used in the decoder.
            Length of the list should be the same as **encoder_depth**
        decoder_use_batchnorm: If **True**, BatchNorm2d layer between Conv2D and Activation layers
            is used. If **"inplace"** InplaceABN will be used, allows to decrease memory consumption.
            Available options are **True, False, "inplace"**
        decoder_attention_type: Attention module used in decoder of the model (in addition to the built-in attention used to
            process skip connection feature maps). Available options are **None**, **se** and **scse**.
            SE paper - https://arxiv.org/abs/1709.01507
            SCSE paper - https://arxiv.org/abs/1808.08127
        in_channels: The number of input channels of the model, default is 3 (RGB images)
        classes: The number of classes of the output mask. Can be thought of as the number of channels of the mask
        activation: An activation function to apply after the final convolution layer.
            Available options are **"sigmoid"**, **"softmax"**, **"logsoftmax"**, **"tanh"**, **"identity"**, **callable** and **None**.
            Default is **None**
        aux_params: Dictionary with parameters of the auxiliary output (classification head). Auxiliary output is build 
            on top of encoder if **aux_params** is not **None** (default). Supported params:
                - classes (int): A number of classes
                - pooling (str): One of "max", "avg". Default is "avg"
                - dropout (float): Dropout factor in [0, 1)
                - activation (str): An activation function to apply "sigmoid"/"softmax" (could be **None** to return logits)

    Returns:
        ``torch.nn.Module``: ResUnetPlusPlus

    .. _EfficientUnetPlusPlus:
        https://arxiv.org/abs/1911.07067

    Reference:
        https://arxiv.org/abs/1911.07067
    """

    def __init__(
        self,
        encoder_name: str = "timm-efficientnet-b5",
        encoder_depth: int = 5,
        encoder_weights: Optional[str] = "imagenet",
        decoder_channels: List[int] = (256, 128, 64, 32, 16),
        squeeze_ratio: int = 1,
        expansion_ratio: int = 1,
        in_channels: int = 3,
        classes: int = 1,
        activation: Optional[Union[str, callable]] = None,
        aux_params: Optional[dict] = None,
    ):
        super().__init__()
        self.classes = classes
        self.encoder = get_encoder(
            encoder_name,
            in_channels=in_channels,
            depth=encoder_depth,
            weights=encoder_weights,
        )

        self.decoder = EfficientUnetPlusPlusDecoder(
            encoder_channels=self.encoder.out_channels,
            decoder_channels=decoder_channels,
            n_blocks=encoder_depth,
            squeeze_ratio=squeeze_ratio,
            expansion_ratio=expansion_ratio
        )

        self.segmentation_head = SegmentationHead(
            in_channels=decoder_channels[-1],
            out_channels=classes,
            activation=activation,
            kernel_size=3,
        )

        if aux_params is not None:
            self.classification_head = ClassificationHead(
                in_channels=self.encoder.out_channels[-1], **aux_params
            )
        else:
            self.classification_head = None

        self.name = "EfficientUNet++-{}".format(encoder_name)
        self.initialize()

    def predict(self, x):
        """Inference method. Switch model to `eval` mode, call `.forward(x)` with `torch.no_grad()`

        Args:
            x: 4D torch tensor with shape (batch_size, channels, height, width)

        Return:
            prediction: 4D torch tensor with shape (batch_size, classes, height, width)

        """
        if self.training:
            self.eval()

        with torch.no_grad():
            output = self.forward(x)

        if self.classes > 1:
            probs = torch.softmax(output, dim=1)
        else:
            probs = torch.sigmoid(output)

        probs = probs.squeeze(0)
        tf = transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.Resize(x.size[1]),
                transforms.ToTensor()
            ]
        )
        full_mask = tf(probs.cpu())   

        return full_mask