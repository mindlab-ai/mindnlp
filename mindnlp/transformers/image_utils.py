# coding=utf-8
# Copyright 2021 The HuggingFace Inc. team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================

"""image utils"""
import base64
import os
from io import BytesIO
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple, Union

import numpy as np
import requests
from packaging import version

from mindnlp.utils import (
    ExplicitEnum,
    is_mindspore_available,
    is_mindspore_tensor,
    is_vision_available,
    logging,
    requires_backends,
    to_numpy,
)


if is_vision_available():
    import PIL.Image
    import PIL.ImageOps

    if version.parse(version.parse(PIL.__version__).base_version) >= version.parse("9.1.0"):
        PILImageResampling = PIL.Image.Resampling
    else:
        PILImageResampling = PIL.Image

if TYPE_CHECKING:
    if is_mindspore_available():
        import mindspore


logger = logging.get_logger(__name__)


ImageInput = Union[
    "PIL.Image.Image", np.ndarray, "mindspore.Tensor", List["PIL.Image.Image"], List[np.ndarray], List["mindspore.Tensor"]
]  # noqa


class ChannelDimension(ExplicitEnum):

    """
    Represents a channel dimension for data analysis and visualization.
    
    This class inherits from ExplicitEnum and provides a set of predefined channel dimensions. It allows for easy management and manipulation of channel dimensions within a data processing or visualization context.
    
    Attributes:
        - TODO: List any attributes specific to the ChannelDimension class.
    
    Methods:
        - TODO: List any methods specific to the ChannelDimension class.
    
    """
    FIRST = "channels_first"
    LAST = "channels_last"


class AnnotationFormat(ExplicitEnum):

    """
    Represents an annotation format for storing and manipulating data.
    
    This class is a subclass of ExplicitEnum, which allows for the creation of enumerated types with explicit values. The AnnotationFormat class provides a way to define and manage different annotation formats used in data processing and analysis.
    
    Attributes:
        name (str): The name of the annotation format.
        description (str): A brief description of the annotation format.
        file_extension (str): The file extension associated with the annotation format.
    
    Methods:
        load(file_path): Loads an annotation file in the specified format.
        save(file_path): Saves an annotation file in the specified format.
        validate(): Validates the current annotation format.
    
    Example usage:
        >>> format = AnnotationFormat(name="XML", description="Annotation data stored in XML format", file_extension=".xml")
        >>> format.load("annotations.xml")
        >>> format.save("annotations.xml")
        >>> format.validate()
    
    """
    COCO_DETECTION = "coco_detection"
    COCO_PANOPTIC = "coco_panoptic"


class AnnotionFormat(ExplicitEnum):

    """
    Represents a class for defining annotation formats. This class inherits from ExplicitEnum.
    
    AnnotionFormat provides a way to define and manage different annotation formats. It inherits properties and methods from the ExplicitEnum class, allowing for easy management and manipulation of annotation formats within a Python application.
    
    Attributes:
        ExplicitEnum: The base class from which AnnotionFormat inherits.
    
    Usage:
        AnnotionFormat instances can be used to define and manage annotation formats within a Python application. The class provides methods and properties for working with annotation formats in a structured and consistent manner.
    
    Example:
        
        # Define a new annotation format
        class MyAnnotationFormat(AnnotionFormat):
            JSON = 'json'
            XML = 'xml'
        
    
    Note:
        It is recommended to use AnnotionFormat for defining annotation formats to ensure consistent usage and management within the application.
    """
    COCO_DETECTION = AnnotationFormat.COCO_DETECTION.value
    COCO_PANOPTIC = AnnotationFormat.COCO_PANOPTIC.value


AnnotationType = Dict[str, Union[int, str, List[Dict]]]


def is_pil_image(img):

    """
    This function checks if the input 'img' is a PIL Image. 
    
    Args:
        img (PIL.Image.Image): The input image to be checked.
    
    Returns:
        None: This function does not return any value.
    
    Raises:
        None
    """
    return is_vision_available() and isinstance(img, PIL.Image.Image)


def is_valid_image(img):

    """
    Checks if the provided image is valid.
    
    Args:
        img (object): The image to be checked for validity. It can be an instance of PIL.Image.Image, np.ndarray, or a MindSpore tensor.
    
    Returns:
        None: This function does not return any value.
    
    Raises:
        None: This function does not raise any exceptions.
    """
    return (
        (is_vision_available() and isinstance(img, PIL.Image.Image))
        or isinstance(img, np.ndarray)
        or is_mindspore_tensor(img)
    )


def valid_images(imgs):

    """Validate a list of images.
    
    Args:
        imgs (list or tuple): A list of image objects to be validated.
    
    Returns:
        None: This function does not return any value.
    
    Raises:
        TypeError: If the input parameter is not a list or tuple.
        ValueError: If any of the images in the list are invalid.
    """
    # If we have an list of images, make sure every image is valid
    if isinstance(imgs, (list, tuple)):
        for img in imgs:
            if not valid_images(img):
                return False
    # If not a list of tuple, we have been given a single image or batched tensor of images
    elif not is_valid_image(imgs):
        return False
    return True


def is_batched(img):

    """
    Checks if the input is a batch of images.
    
    Args:
        img (list or tuple): The input image or a batch of images to be checked.
        
    Returns:
        None: Returns None if the input is not a batch of images.
    
    Raises:
        None
    """
    if isinstance(img, (list, tuple)):
        return is_valid_image(img[0])
    return False


def is_scaled_image(image: np.ndarray) -> bool:
    """
    Checks to see whether the pixel values have already been rescaled to [0, 1].
    """
    if image.dtype == np.uint8:
        return False

    # It's possible the image has pixel values in [0, 255] but is of floating type
    return np.min(image) >= 0 and np.max(image) <= 1


def make_list_of_images(images, expected_ndims: int = 3) -> List[ImageInput]:
    """
    Ensure that the input is a list of images. If the input is a single image, it is converted to a list of length 1.
    If the input is a batch of images, it is converted to a list of images.

    Args:
        images (`ImageInput`):
            Image of images to turn into a list of images.
        expected_ndims (`int`, *optional*, defaults to 3):
            Expected number of dimensions for a single input image. If the input image has a different number of
            dimensions, an error is raised.
    """
    if is_batched(images):
        return images

    # Either the input is a single image, in which case we create a list of length 1
    if isinstance(images, PIL.Image.Image):
        # PIL images are never batched
        return [images]

    if is_valid_image(images):
        if images.ndim == expected_ndims + 1:
            # Batch of images
            images = list(images)
        elif images.ndim == expected_ndims:
            # Single image
            images = [images]
        else:
            raise ValueError(
                f"Invalid image shape. Expected either {expected_ndims + 1} or {expected_ndims} dimensions, but got"
                f" {images.ndim} dimensions."
            )
        return images
    raise ValueError(
        "Invalid image type. Expected either PIL.Image.Image, numpy.ndarray, mindspore.Tensor, tf.Tensor or "
        f"jax.ndarray, but got {type(images)}."
    )


def to_numpy_array(img) -> np.ndarray:

    """
    Converts an image to a NumPy array.
    
    Args:
        img (object): The image to be converted. It should be a valid image object.
        
    Returns:
        np.ndarray: A NumPy array representation of the image.
        
    Raises:
        ValueError: If the image type is invalid.
        Exception: If any exceptions occur during the conversion process.
    """
    if not is_valid_image(img):
        raise ValueError(f"Invalid image type: {type(img)}")

    if is_vision_available() and isinstance(img, PIL.Image.Image):
        return np.array(img)
    return to_numpy(img)


def infer_channel_dimension_format(
    image: np.ndarray, num_channels: Optional[Union[int, Tuple[int, ...]]] = None
) -> ChannelDimension:
    """
    Infers the channel dimension format of `image`.

    Args:
        image (`np.ndarray`):
            The image to infer the channel dimension of.
        num_channels (`int` or `Tuple[int, ...]`, *optional*, defaults to `(1, 3)`):
            The number of channels of the image.

    Returns:
        The channel dimension of the image.
    """
    num_channels = num_channels if num_channels is not None else (1, 3)
    num_channels = (num_channels,) if isinstance(num_channels, int) else num_channels

    if image.ndim == 3:
        first_dim, last_dim = 0, 2
    elif image.ndim == 4:
        first_dim, last_dim = 1, 3
    else:
        raise ValueError(f"Unsupported number of image dimensions: {image.ndim}")

    if image.shape[first_dim] in num_channels:
        return ChannelDimension.FIRST
    elif image.shape[last_dim] in num_channels:
        return ChannelDimension.LAST
    raise ValueError("Unable to infer channel dimension format")


def get_channel_dimension_axis(
    image: np.ndarray, input_data_format: Optional[Union[ChannelDimension, str]] = None
) -> int:
    """
    Returns the channel dimension axis of the image.

    Args:
        image (`np.ndarray`):
            The image to get the channel dimension axis of.
        input_data_format (`ChannelDimension` or `str`, *optional*):
            The channel dimension format of the image. If `None`, will infer the channel dimension from the image.

    Returns:
        The channel dimension axis of the image.
    """
    if input_data_format is None:
        input_data_format = infer_channel_dimension_format(image)
    if input_data_format == ChannelDimension.FIRST:
        return image.ndim - 3
    elif input_data_format == ChannelDimension.LAST:
        return image.ndim - 1
    raise ValueError(f"Unsupported data format: {input_data_format}")


def get_image_size(image: np.ndarray, channel_dim: ChannelDimension = None) -> Tuple[int, int]:
    """
    Returns the (height, width) dimensions of the image.

    Args:
        image (`np.ndarray`):
            The image to get the dimensions of.
        channel_dim (`ChannelDimension`, *optional*):
            Which dimension the channel dimension is in. If `None`, will infer the channel dimension from the image.

    Returns:
        A tuple of the image's height and width.
    """
    if channel_dim is None:
        channel_dim = infer_channel_dimension_format(image)

    if channel_dim == ChannelDimension.FIRST:
        return image.shape[-2], image.shape[-1]
    elif channel_dim == ChannelDimension.LAST:
        return image.shape[-3], image.shape[-2]
    else:
        raise ValueError(f"Unsupported data format: {channel_dim}")


def is_valid_annotation_coco_detection(annotation: Dict[str, Union[List, Tuple]]) -> bool:

    """
    Args:
        annotation (dict): A dictionary representing an annotation with the following keys:
            - 'image_id': An identifier for the image associated with the annotation.
            - 'annotations': A list or tuple of annotations associated with the image.
    Returns:
        bool: Returns True if the annotation is valid for COCO detection, False otherwise.
    Raises:
        None
    """
    if (
        isinstance(annotation, dict)
        and "image_id" in annotation
        and "annotations" in annotation
        and isinstance(annotation["annotations"], (list, tuple))
        and (
            # an image can have no annotations
            len(annotation["annotations"]) == 0 or isinstance(annotation["annotations"][0], dict)
        )
    ):
        return True
    return False


def is_valid_annotation_coco_panoptic(annotation: Dict[str, Union[List, Tuple]]) -> bool:

    """
    Checks if the given COCO Panoptic annotation is valid.
    
    Args:
        annotation (Dict[str, Union[List, Tuple]]): A dictionary representing a COCO Panoptic annotation containing the keys 'image_id', 'segments_info', and 'file_name'. The value associated with the key 'segments_info' must be a list or tuple, and if it is not empty, the first element must be a dictionary.
    
    Returns:
        bool: True if the annotation is valid, otherwise False.
    
    Raises:
        None
    """
    if (
        isinstance(annotation, dict)
        and "image_id" in annotation
        and "segments_info" in annotation
        and "file_name" in annotation
        and isinstance(annotation["segments_info"], (list, tuple))
        and (
            # an image can have no segments
            len(annotation["segments_info"]) == 0 or isinstance(annotation["segments_info"][0], dict)
        )
    ):
        return True
    return False


def valid_coco_detection_annotations(annotations: Iterable[Dict[str, Union[List, Tuple]]]) -> bool:

    """
    Check if a collection of COCO-style annotation dictionaries for object detection is valid.
    
    Args:
        annotations (Iterable[Dict[str, Union[List, Tuple]]]): A collection of COCO-style annotation dictionaries.
            Each dictionary should contain information about the annotations for a single object or image.
            The annotations should follow the COCO annotation format, which includes keys such as 'image_id',
            'category_id', 'bbox', etc.
    
    Returns:
        bool: True if all the annotations are valid according to the COCO detection annotation format,
        False otherwise.
    
    Raises:
        None.
    
    Note:
        The function uses the 'is_valid_annotation_coco_detection' function to check the validity of each annotation.
        This function should be implemented separately and should return True or False based on the validity of an individual annotation.
    """
    return all(is_valid_annotation_coco_detection(ann) for ann in annotations)


def valid_coco_panoptic_annotations(annotations: Iterable[Dict[str, Union[List, Tuple]]]) -> bool:

    """
    Checks if the given Coco Panoptic annotations are valid.
    
    Args:
        annotations (Iterable[Dict[str, Union[List, Tuple]]]): A collection of Coco Panoptic annotations to be validated.
    
    Returns:
        bool: True if all annotations are valid, False otherwise.
    
    Raises:
        None.
    """
    return all(is_valid_annotation_coco_panoptic(ann) for ann in annotations)


def load_image(image: Union[str, "PIL.Image.Image"], timeout: Optional[float] = None) -> "PIL.Image.Image":
    """
    Loads `image` to a PIL Image.

    Args:
        image (`str` or `PIL.Image.Image`):
            The image to convert to the PIL Image format.
        timeout (`float`, *optional*):
            The timeout value in seconds for the URL request.

    Returns:
        `PIL.Image.Image`: A PIL Image.
    """
    requires_backends(load_image, ["vision"])
    if isinstance(image, str):
        if image.startswith("http://") or image.startswith("https://"):
            # We need to actually check for a real protocol, otherwise it's impossible to use a local file
            # like http_hf-mirror.com.png
            image = PIL.Image.open(requests.get(image, stream=True, timeout=timeout).raw)
        elif os.path.isfile(image):
            image = PIL.Image.open(image)
        else:
            if image.startswith("data:image/"):
                image = image.split(",")[1]

            # Try to load as base64
            try:
                b64 = base64.b64decode(image, validate=True)
                image = PIL.Image.open(BytesIO(b64))
            except Exception as e:
                raise ValueError(
                    f"Incorrect image source. Must be a valid URL starting with `http://` or `https://`, a valid path to an image file, or a base64 encoded string. Got {image}. Failed with {e}"
                ) from e
    elif isinstance(image, PIL.Image.Image):
        pass
    else:
        raise ValueError(
            "Incorrect format used for image. Should be an url linking to an image, a base64 string, a local path, or a PIL image."
        )
    image = PIL.ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    return image


def validate_preprocess_arguments(
    do_rescale: Optional[bool] = None,
    rescale_factor: Optional[float] = None,
    do_normalize: Optional[bool] = None,
    image_mean: Optional[Union[float, List[float]]] = None,
    image_std: Optional[Union[float, List[float]]] = None,
    do_pad: Optional[bool] = None,
    size_divisibility: Optional[int] = None,
    do_center_crop: Optional[bool] = None,
    crop_size: Optional[Dict[str, int]] = None,
    do_resize: Optional[bool] = None,
    size: Optional[Dict[str, int]] = None,
    resample: Optional["PILImageResampling"] = None,
):
    """
    Checks validity of typically used arguments in an `ImageProcessor` `preprocess` method.
    Raises `ValueError` if arguments incompatibility is caught.
    Many incompatibilities are model-specific. `do_pad` sometimes needs `size_divisor`,
    sometimes `size_divisibility`, and sometimes `size`. New models and processors added should follow
    existing arguments when possible.

    """
    if do_rescale and rescale_factor is None:
        raise ValueError("rescale_factor must be specified if do_rescale is True.")

    if do_pad and size_divisibility is None:
        # Here, size_divisor might be passed as the value of size
        raise ValueError(
            "Depending on moel, size_divisibility, size_divisor, pad_size or size must be specified if do_pad is True."
        )

    if do_normalize and (image_mean is None or image_std is None):
        raise ValueError("image_mean and image_std must both be specified if do_normalize is True.")

    if do_center_crop and crop_size is None:
        raise ValueError("crop_size must be specified if do_center_crop is True.")

    if do_resize and (size is None or resample is None):
        raise ValueError("size and resample must be specified if do_resize is True.")


# In the future we can add a TF implementation here when we have TF models.
class ImageFeatureExtractionMixin:
    """
    Mixin that contain utilities for preparing image features.
    """

    def _ensure_format_supported(self, image):

        """
        This method '_ensure_format_supported' in the class 'ImageFeatureExtractionMixin' ensures that the input image format is supported for further processing.
        
        Args:
            self: The instance of the class.
            image: The input image to be checked for supported format. It can be either a PIL image object of type 'PIL.Image.Image', a numpy array of type 'np.ndarray', or a mindspore tensor. 
                If the input image is not of any of these types, a ValueError will be raised.
        
        Returns:
            None. This method does not return any value.
        
        Raises:
            ValueError: Raised when the input image is not of type 'PIL.Image.Image', 'np.ndarray', or 'mindspore.Tensor'.
        """
        if not isinstance(image, (PIL.Image.Image, np.ndarray)) and not is_mindspore_tensor(image):
            raise ValueError(
                f"Got type {type(image)} which is not supported, only `PIL.Image.Image`, `np.array` and "
                "`mindspore.Tensor` are."
            )

    def to_pil_image(self, image, rescale=None):
        """
        Converts `image` to a PIL Image. Optionally rescales it and puts the channel dimension back as the last axis if
        needed.

        Args:
            image (`PIL.Image.Image` or `numpy.ndarray` or `mindspore.Tensor`):
                The image to convert to the PIL Image format.
            rescale (`bool`, *optional*):
                Whether or not to apply the scaling factor (to make pixel values integers between 0 and 255). Will
                default to `True` if the image type is a floating type, `False` otherwise.
        """
        self._ensure_format_supported(image)

        if is_mindspore_tensor(image):
            image = image.numpy()

        if isinstance(image, np.ndarray):
            if rescale is None:
                # rescale default to the array being of floating type.
                rescale = isinstance(image.flat[0], np.floating)
            # If the channel as been moved to first dim, we put it back at the end.
            if image.ndim == 3 and image.shape[0] in [1, 3]:
                image = image.transpose(1, 2, 0)
            if rescale:
                image = image * 255
            image = image.astype(np.uint8)
            return PIL.Image.fromarray(image)
        return image

    def convert_rgb(self, image):
        """
        Converts `PIL.Image.Image` to RGB format.

        Args:
            image (`PIL.Image.Image`):
                The image to convert.
        """
        self._ensure_format_supported(image)
        if not isinstance(image, PIL.Image.Image):
            return image

        return image.convert("RGB")

    def rescale(self, image: np.ndarray, scale: Union[float, int]) -> np.ndarray:
        """
        Rescale a numpy image by scale amount
        """
        self._ensure_format_supported(image)
        return image * scale

    def to_numpy_array(self, image, rescale=None, channel_first=True):
        """
        Converts `image` to a numpy array. Optionally rescales it and puts the channel dimension as the first
        dimension.

        Args:
            image (`PIL.Image.Image` or `np.ndarray` or `mindspore.Tensor`):
                The image to convert to a NumPy array.
            rescale (`bool`, *optional*):
                Whether or not to apply the scaling factor (to make pixel values floats between 0. and 1.). Will
                default to `True` if the image is a PIL Image or an array/tensor of integers, `False` otherwise.
            channel_first (`bool`, *optional*, defaults to `True`):
                Whether or not to permute the dimensions of the image to put the channel dimension first.
        """
        self._ensure_format_supported(image)

        if isinstance(image, PIL.Image.Image):
            image = np.array(image)

        if is_mindspore_tensor(image):
            image = image.numpy()

        rescale = isinstance(image.flat[0], np.integer) if rescale is None else rescale

        if rescale:
            image = self.rescale(image.astype(np.float32), 1 / 255.0)

        if channel_first and image.ndim == 3:
            image = image.transpose(2, 0, 1)

        return image

    def expand_dims(self, image):
        """
        Expands 2-dimensional `image` to 3 dimensions.

        Args:
            image (`PIL.Image.Image` or `np.ndarray` or `mindspore.Tensor`):
                The image to expand.
        """
        self._ensure_format_supported(image)

        # Do nothing if PIL image
        if isinstance(image, PIL.Image.Image):
            return image

        if is_mindspore_tensor(image):
            image = image.unsqueeze(0)
        else:
            image = np.expand_dims(image, axis=0)
        return image

    def normalize(self, image, mean, std, rescale=False):
        """
        Normalizes `image` with `mean` and `std`. Note that this will trigger a conversion of `image` to a NumPy array
        if it's a PIL Image.

        Args:
            image (`PIL.Image.Image` or `np.ndarray` or `mindspore.Tensor`):
                The image to normalize.
            mean (`List[float]` or `np.ndarray` or `mindspore.Tensor`):
                The mean (per channel) to use for normalization.
            std (`List[float]` or `np.ndarray` or `mindspore.Tensor`):
                The standard deviation (per channel) to use for normalization.
            rescale (`bool`, *optional*, defaults to `False`):
                Whether or not to rescale the image to be between 0 and 1. If a PIL image is provided, scaling will
                happen automatically.
        """
        self._ensure_format_supported(image)

        if isinstance(image, PIL.Image.Image):
            image = self.to_numpy_array(image, rescale=True)
        # If the input image is a PIL image, it automatically gets rescaled. If it's another
        # type it may need rescaling.
        elif rescale:
            if isinstance(image, np.ndarray):
                image = self.rescale(image.astype(np.float32), 1 / 255.0)
            elif is_mindspore_tensor(image):
                image = self.rescale(image.float(), 1 / 255.0)

        if isinstance(image, np.ndarray):
            if not isinstance(mean, np.ndarray):
                mean = np.array(mean).astype(image.dtype)
            if not isinstance(std, np.ndarray):
                std = np.array(std).astype(image.dtype)
        elif is_mindspore_tensor(image):
            import mindspore
            if not isinstance(mean, mindspore.Tensor):
                mean = mindspore.tensor(mean)
            if not isinstance(std, mindspore.Tensor):
                std = mindspore.tensor(std)

        if image.ndim == 3 and image.shape[0] in [1, 3]:
            return (image - mean[:, None, None]) / std[:, None, None]
        else:
            return (image - mean) / std

    def resize(self, image, size, resample=None, default_to_square=True, max_size=None):
        """
        Resizes `image`. Enforces conversion of input to PIL.Image.

        Args:
            image (`PIL.Image.Image` or `np.ndarray` or `mindspore.Tensor`):
                The image to resize.
            size (`int` or `Tuple[int, int]`):
                The size to use for resizing the image. If `size` is a sequence like (h, w), output size will be
                matched to this.

                If `size` is an int and `default_to_square` is `True`, then image will be resized to (size, size). If
                `size` is an int and `default_to_square` is `False`, then smaller edge of the image will be matched to
                this number. i.e, if height > width, then image will be rescaled to (size * height / width, size).
            resample (`int`, *optional*, defaults to `PILImageResampling.BILINEAR`):
                The filter to user for resampling.
            default_to_square (`bool`, *optional*, defaults to `True`):
                How to convert `size` when it is a single int. If set to `True`, the `size` will be converted to a
                square (`size`,`size`). If set to `False`, will replicate
                [`torchvision.transforms.Resize`](https://pytorch.org/vision/stable/transforms.html#torchvision.transforms.Resize)
                with support for resizing only the smallest edge and providing an optional `max_size`.
            max_size (`int`, *optional*, defaults to `None`):
                The maximum allowed for the longer edge of the resized image: if the longer edge of the image is
                greater than `max_size` after being resized according to `size`, then the image is resized again so
                that the longer edge is equal to `max_size`. As a result, `size` might be overruled, i.e the smaller
                edge may be shorter than `size`. Only used if `default_to_square` is `False`.

        Returns:
            image: A resized `PIL.Image.Image`.
        """
        resample = resample if resample is not None else PILImageResampling.BILINEAR

        self._ensure_format_supported(image)

        if not isinstance(image, PIL.Image.Image):
            image = self.to_pil_image(image)

        if isinstance(size, list):
            size = tuple(size)

        if isinstance(size, int) or len(size) == 1:
            if default_to_square:
                size = (size, size) if isinstance(size, int) else (size[0], size[0])
            else:
                width, height = image.size
                # specified size only for the smallest edge
                short, long = (width, height) if width <= height else (height, width)
                requested_new_short = size if isinstance(size, int) else size[0]

                if short == requested_new_short:
                    return image

                new_short, new_long = requested_new_short, int(requested_new_short * long / short)

                if max_size is not None:
                    if max_size <= requested_new_short:
                        raise ValueError(
                            f"max_size = {max_size} must be strictly greater than the requested "
                            f"size for the smaller edge size = {size}"
                        )
                    if new_long > max_size:
                        new_short, new_long = int(max_size * new_short / new_long), max_size

                size = (new_short, new_long) if width <= height else (new_long, new_short)

        return image.resize(size, resample=resample)

    def center_crop(self, image, size):
        """
        Crops `image` to the given size using a center crop. Note that if the image is too small to be cropped to the
        size given, it will be padded (so the returned result has the size asked).

        Args:
            image (`PIL.Image.Image` or `np.ndarray` or `mindspore.Tensor` of shape (n_channels, height, width) or (height, width, n_channels)):
                The image to resize.
            size (`int` or `Tuple[int, int]`):
                The size to which crop the image.

        Returns:
            new_image: A center cropped `PIL.Image.Image` or `np.ndarray` or `mindspore.Tensor` of shape: (n_channels,
            height, width).
        """
        self._ensure_format_supported(image)

        if not isinstance(size, tuple):
            size = (size, size)

        # PIL Image.size is (width, height) but NumPy array and torch Tensors have (height, width)
        if is_mindspore_tensor(image) or isinstance(image, np.ndarray):
            if image.ndim == 2:
                image = self.expand_dims(image)
            image_shape = image.shape[1:] if image.shape[0] in [1, 3] else image.shape[:2]
        else:
            image_shape = (image.size[1], image.size[0])

        top = (image_shape[0] - size[0]) // 2
        bottom = top + size[0]  # In case size is odd, (image_shape[0] + size[0]) // 2 won't give the proper result.
        left = (image_shape[1] - size[1]) // 2
        right = left + size[1]  # In case size is odd, (image_shape[1] + size[1]) // 2 won't give the proper result.

        # For PIL Images we have a method to crop directly.
        if isinstance(image, PIL.Image.Image):
            return image.crop((left, top, right, bottom))

        # Check if image is in (n_channels, height, width) or (height, width, n_channels) format
        channel_first = image.shape[0] in [1, 3]
        # Transpose (height, width, n_channels) format images
        if not channel_first:
            if isinstance(image, np.ndarray):
                image = image.transpose(2, 0, 1)
            if is_mindspore_tensor(image):
                image = image.permute(2, 0, 1)

        # Check if cropped area is within image boundaries
        if top >= 0 and bottom <= image_shape[0] and left >= 0 and right <= image_shape[1]:
            return image[..., top:bottom, left:right]

        # Otherwise, we may need to pad if the image is too small. Oh joy...
        new_shape = image.shape[:-2] + (max(size[0], image_shape[0]), max(size[1], image_shape[1]))
        if isinstance(image, np.ndarray):
            new_image = np.zeros_like(image, shape=new_shape)
        elif is_mindspore_tensor(image):
            new_image = image.new_zeros(new_shape)

        top_pad = (new_shape[-2] - image_shape[0]) // 2
        bottom_pad = top_pad + image_shape[0]
        left_pad = (new_shape[-1] - image_shape[1]) // 2
        right_pad = left_pad + image_shape[1]
        new_image[..., top_pad:bottom_pad, left_pad:right_pad] = image

        top += top_pad
        bottom += top_pad
        left += left_pad
        right += left_pad

        new_image = new_image[
            ..., max(0, top) : min(new_image.shape[-2], bottom), max(0, left) : min(new_image.shape[-1], right)
        ]

        return new_image

    def flip_channel_order(self, image):
        """
        Flips the channel order of `image` from RGB to BGR, or vice versa. Note that this will trigger a conversion of
        `image` to a NumPy array if it's a PIL Image.

        Args:
            image (`PIL.Image.Image` or `np.ndarray` or `mindspore.Tensor`):
                The image whose color channels to flip. If `np.ndarray` or `mindspore.Tensor`, the channel dimension should
                be first.
        """
        self._ensure_format_supported(image)

        if isinstance(image, PIL.Image.Image):
            image = self.to_numpy_array(image)

        return image[::-1, :, :]

    def rotate(self, image, angle, resample=None, expand=0, center=None, translate=None, fillcolor=None):
        """
        Returns a rotated copy of `image`. This method returns a copy of `image`, rotated the given number of degrees
        counter clockwise around its centre.

        Args:
            image (`PIL.Image.Image` or `np.ndarray` or `mindspore.Tensor`):
                The image to rotate. If `np.ndarray` or `mindspore.Tensor`, will be converted to `PIL.Image.Image` before
                rotating.

        Returns:
            image: A rotated `PIL.Image.Image`.
        """
        resample = resample if resample is not None else PIL.Image.NEAREST

        self._ensure_format_supported(image)

        if not isinstance(image, PIL.Image.Image):
            image = self.to_pil_image(image)

        return image.rotate(
            angle, resample=resample, expand=expand, center=center, translate=translate, fillcolor=fillcolor
        )


def promote_annotation_format(annotation_format: Union[AnnotionFormat, AnnotationFormat]) -> AnnotationFormat:

    """
    Promotes the given annotation format to a higher level.
    
    Args:
        annotation_format (Union[AnnotionFormat, AnnotationFormat]): The annotation format to be promoted. It can be either an instance of AnnotionFormat or AnnotationFormat.
    
    Returns:
        AnnotationFormat: The promoted annotation format.
    
    Raises:
        None.
    
    """
    # can be removed when `AnnotionFormat` is fully deprecated
    return AnnotationFormat(annotation_format.value)


def validate_annotations(
    annotation_format: AnnotationFormat,
    supported_annotation_formats: Tuple[AnnotationFormat, ...],
    annotations: List[Dict],
) -> None:

    """
    Validate the given annotations against the specified annotation format and supported formats.
    
    Args:
        annotation_format (AnnotationFormat): The format of the annotations to be validated.
        supported_annotation_formats (Tuple[AnnotationFormat, ...]): A tuple of supported annotation formats.
        annotations (List[Dict]): The annotations to be validated.
    
    Returns:
        None: This function does not return any value.
    
    Raises:
        ValueError: If the annotation format is not supported or if the annotations are invalid for the specified format.
        DeprecatedWarning: If the annotation format is deprecated and will be removed in the future version.
    """
    if isinstance(annotation_format, AnnotionFormat):
        logger.warning_once(
            f"`{annotation_format.__class__.__name__}` is deprecated and will be removed in v4.38. "
            f"Please use `{AnnotationFormat.__name__}` instead."
        )
        annotation_format = promote_annotation_format(annotation_format)

    if annotation_format not in supported_annotation_formats:
        raise ValueError(f"Unsupported annotation format: {format} must be one of {supported_annotation_formats}")

    if annotation_format is AnnotationFormat.COCO_DETECTION:
        if not valid_coco_detection_annotations(annotations):
            raise ValueError(
                "Invalid COCO detection annotations. Annotations must a dict (single image) or list of dicts "
                "(batch of images) with the following keys: `image_id` and `annotations`, with the latter "
                "being a list of annotations in the COCO format."
            )

    if annotation_format is AnnotationFormat.COCO_PANOPTIC:
        if not valid_coco_panoptic_annotations(annotations):
            raise ValueError(
                "Invalid COCO panoptic annotations. Annotations must a dict (single image) or list of dicts "
                "(batch of images) with the following keys: `image_id`, `file_name` and `segments_info`, with "
                "the latter being a list of annotations in the COCO format."
            )


def validate_kwargs(valid_processor_keys: List[str], captured_kwargs: List[str]):

    """
    Validate the captured keyword arguments against the valid processor keys.
    
    Args:
        valid_processor_keys (List[str]): A list of valid keys that the captured kwargs should match against.
        captured_kwargs (List[str]): A list of captured keyword arguments to be validated.
    
    Returns:
        None: This function does not return anything.
    
    Raises:
        None
    """
    unused_keys = set(captured_kwargs).difference(set(valid_processor_keys))
    if unused_keys:
        unused_key_str = ", ".join(unused_keys)
        # TODO raise a warning here instead of simply logging?
        logger.warning(f"Unused or unrecognized kwargs: {unused_key_str}.")
