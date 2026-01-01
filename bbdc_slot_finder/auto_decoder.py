#!/usr/bin/python3
# coding: utf-8
import os
import pytesseract
import argparse
from bbdc_slot_finder.logger import logger
from collections import Counter
import numpy as np

try:
    import Image, ImageOps, ImageFilter, imread
except ImportError:
    from PIL import Image, ImageOps, ImageFilter
from io import BytesIO
import base64

DEBUG = os.environ.get("BBDC_BOT_DEBUG", False)


def auto_solve_captcha_data(captcha_data):
    bio = get_captcha_image(captcha_data)
    captcha = get_captcha(bio, auto=True)
    return captcha


def get_captcha_image(captcha_data):
    img_data = captcha_data["image"].split(",")[1]
    if not DEBUG:
        with open("logs/captcha.txt", "a+") as f:
            f.write(img_data + "\n")
    bio = base64img(img_data)
    return bio


def calculate_noise_count(img_obj, w, h):
    """
    计算邻域非白色的个数
    Args:
        img_obj: img obj
        w: width
        h: height
    Returns:
        count (int)
    """
    count = 0
    width, height, s = img_obj.shape
    for _w_ in [w - 1, w, w + 1]:
        for _h_ in [h - 1, h, h + 1]:
            if _w_ >= width - 1:
                continue
            if _h_ >= height - 1:
                continue
            if _w_ == w and _h_ == h:
                continue
            if (
                (img_obj[_w_, _h_, 0] <= 233)
                or (img_obj[_w_, _h_, 1] <= 233)
                or (img_obj[_w_, _h_, 2] <= 233)
            ):
                count += 1
    return count


def operate_img(img, k):
    w, h, s = img.shape
    # 从高度开始遍历
    for _w in range(w):
        # 遍历宽度
        for _h in range(h):
            if _h != 0 and _w != 0 and _w <= w - 1 and _h <= h - 1:
                if calculate_noise_count(img, _w, _h) <= k:
                    img[_w, _h, 0] = 255
                    img[_w, _h, 1] = 255
                    img[_w, _h, 2] = 255

    return img


def solve_captcha(path, debug=False):
    """
    Convert a captcha image into a text,
    using PyTesseract Python-wrapper for Tesseract
    Arguments:
        path (str):
            path to the image to be processed
    Return:
        'textualized' image

    General Idea:
    1. Get list of all colors in the image
    2. Top 5 common colours consists of letters + background (Most common colour is the background)
    3. Convert all colours that aren't in the top 5 including background to white
    4. Apply Box Blur to fill in gaps and process into B/W image for OCR
    5. Use Tesseract
    """
    image = Image.open(path).convert("RGB")
    # image.convert("RGB")
    image = ImageOps.autocontrast(image)
    # image.show()

    # Get List Of Main Colors
    pixel_count = Counter(image.getdata())
    main_colours = pixel_count.most_common(12)[1:]

    # Filtering Colours
    copy = image.copy()
    pixels = copy.load()
    main_colours_list = list(zip(*main_colours))[0]
    for x in range(image.size[0]):  # For Every Pixel:
        for y in range(image.size[1]):
            if (
                pixels[x, y] not in main_colours_list
            ):  # Change All Non-Main Colour to White
                pixels[x, y] = (255, 255, 255)
    img_dt = np.array(copy)
    img_dt = operate_img(img_dt, 3)
    copy = Image.fromarray(img_dt)
    copy = ImageOps.expand(copy, border=(3, 3), fill="white")
    if debug:
        # copy.show()
        pass

    # Fill holes using box blur then flatten into B/W image
    def fillHoles(text, thresh):
        text = text.filter(ImageFilter.BoxBlur(1))
        fn = lambda x: 255 if x > thresh else 0
        text = text.convert("L").point(fn, mode="1")
        if debug:
            text.show()
        return text

    # OCR Part
    def OCR(image):
        data = pytesseract.image_to_data(
            image,
            output_type="data.frame",
            config=(
                "-c tessedit"
                "_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                " -c tessedit"
                "_char_blacklist=!?"
                " --psm 7"
                " --oem 3"
            ),
        )
        logger.debug(
            "Text: {} | Confidence: {}%".format(data.text[4], int(data.conf[4]))
        )
        return (str(data.text[4]), int(data.conf[4]))

        data = pytesseract.image_to_string(
            image,
            config=(
                "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                " -c tessedict_char_blacklist=!?-_"
                f" --psm 10"
                " --oem 3"
            ),
        )
        logger.debug(f"Auto OCR Text: {data}")
        return str(data).strip("\n ")

    return OCR(fillHoles(copy, 225))


def base64img(encoded_data):
    """decode base64 to bytes img"""
    fh = BytesIO()
    fh.write(base64.b64decode(encoded_data))
    fh.flush()
    return fh


def get_captcha(img, auto=False):
    if auto:
        captcha, conf = solve_captcha(img)
        # logger.info(f"Auto solve captcha: {captcha} with confidence {conf}")
    else:
        Image.open(img).convert("RGB").show()
        captcha = input("Solve Login Captcha: ")
    return captcha


def test(cps):
    with open("logs/captcha.txt", "r") as f:
        cps = f.readlines()
    cps.pop(-1)
    for i in cps:
        img = base64img(i)
        test = solve_captcha(img, debug=True)

    # Fill holes using box blur then flatten into B/W image


def fillHoles(text, thresh):
    text = text.filter(ImageFilter.BoxBlur(1))
    fn = lambda x: 255 if x > thresh else 0
    text = text.convert("L").point(fn, mode="1")
    # text.show()
    return text


def divide_and_conquer_ocr(text):
    import numpy as np
    import cv2

    cv2_img = cv2.cvtColor(np.array(text), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 238, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=lambda c: cv2.boundingRect(c)[0])
    # 循环遍历每个轮廓，保存每个字母
    custom_config = (
        "-c tessedit"
        "_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        + "  --psm 10"
    )
    borders = [
        [0, 0],
    ]
    for i, contour in enumerate(contours):
        # 获取轮廓的边界框 (x, y, w, h)
        x, y, w, h = cv2.boundingRect(contour)
        if borders[-1][1] >= x + w:
            continue
        borders.append([x, x + w])
    if len(borders) > 6:
        # print("wrong!")
        pass
    text = ""
    for i, j in borders[1:]:
        char_image = thresh[:, i:j]
        if char_image.sum() < 10000:
            # print("skip a character!")
            pass
        left_padding = 10  # 左边黑色空间的宽度
        right_padding = 10  # 右边黑色空间的宽度

        char_image = cv2.copyMakeBorder(
            char_image,
            top=0,
            bottom=0,
            left=left_padding,
            right=right_padding,
            borderType=cv2.BORDER_CONSTANT,
            value=[0, 0, 0],
        )
        char_image_pil = Image.fromarray(cv2.cvtColor(char_image, cv2.COLOR_BGR2RGB))
        # char_image_pil.show()
        char = pytesseract.image_to_string(char_image_pil, config=custom_config).strip(
            "\n "
        )
        if len(char):
            char = char[0]
        text += char
    return text


def OCR(image):
    data = pytesseract.image_to_data(
        image,
        output_type="data.frame",
        config=(
            "-c tessedit"
            "_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            " -c tessedit"
            "_char_blacklist=!?"
            " --psm 10"
            " --oem 3"
        ),
    )
    logger.debug("Text: {} | Confidence: {}%".format(data.text[4], int(data.conf[4])))
    return (str(data.text[4]), int(data.conf[4]))

    data = pytesseract.image_to_string(
        image,
        config=(
            "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            " -c tessedict_char_blacklist=!?-_"
            f" --psm 10"
            " --oem 3"
        ),
    )
    logger.debug(f"Auto OCR Text: {data}")
    return str(data).strip("\n ")


if __name__ == "__main__":
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "-i", "--image", required=True, help="path to input image to be OCR'd"
    )
    args = vars(argparser.parse_args())
    path = args["image"]
    print("-- Resolving")
    captcha_text = solve_captcha(path)[0]
    print("-- Result: {}".format(captcha_text))
