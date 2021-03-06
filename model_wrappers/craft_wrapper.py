import sys
import os
sys.path.append(os.path.join(os.getcwd(), "CRAFT-pytorch"))
import cv2
import numpy as np
import craft_utils
import imgproc
import torch

from craft import CRAFT
from collections import OrderedDict
from time import time
from torch.autograd import Variable


class CRAFTWrapper():
    def __init__(self, weights_path):
        self.model = CRAFT()
        self.weights_path = weights_path
        self.cuda = torch.cuda.is_available()
        self.text_threshold = 0.7
        self.link_threshold = 0.4
        self.low_text = 0.4
        self.poly = False
        self.canvas_size = 1280
        self.mag_ratio = 1.5
        self.poly = False
        self.load_model()

    @staticmethod
    def copy_state_dict(state_dict):
        if list(state_dict.keys())[0].startswith("module"):
            start_idx = 1
        else:
            start_idx = 0
        new_state_dict = OrderedDict()
        for k, v in state_dict.items():
            name = ".".join(k.split(".")[start_idx:])
            new_state_dict[name] = v
        return new_state_dict

    def load_model(self):
        if self.cuda:
            self.model.load_state_dict(self.copy_state_dict(torch.load(self.weights_path)))
            self.model = self.model.cuda()
        else:
            self.model.load_state_dict(self.copy_state_dict(torch.load(self.weights_path, map_location='cpu')))
        self.model.eval()

    def detect(self, image):
        start = time()
        image_to_draw = image.copy()

        img_resized, target_ratio, size_heatmap = imgproc.resize_aspect_ratio(image_to_draw, self.canvas_size,
                                                                              interpolation=cv2.INTER_LINEAR,
                                                                              mag_ratio=self.mag_ratio)
        ratio_h = ratio_w = 1 / target_ratio

        h, w, _ = image.shape
        # preprocessing
        x = imgproc.normalizeMeanVariance(img_resized)
        x = torch.from_numpy(x).permute(2, 0, 1)  # [h, w, c] to [c, h, w]
        x = Variable(x.unsqueeze(0))  # [c, h, w] to [b, c, h, w]
        if self.cuda:
            x = x.cuda()

        # forward pass
        with torch.no_grad():
            y, feature = self.model(x)

        # make score and link map
        score_text = y[0, :, :, 0].cpu().data.numpy()
        score_link = y[0, :, :, 1].cpu().data.numpy()

        # Post-processing
        boxes, polys = craft_utils.getDetBoxes(score_text, score_link, self.text_threshold, self.link_threshold, self.low_text, self.poly)

        # coordinate adjustment
        boxes = craft_utils.adjustResultCoordinates(boxes, ratio_w, ratio_h)

        text_parts = []
        for i, box in enumerate(boxes):
            poly = np.array(box).astype(np.int32).reshape((-1))
            poly = poly.reshape(-1, 2)
            x = [int(point[0]) for point in poly]
            y = [int(point[1]) for point in poly]
            min_x = max(0, min(x) - 5)
            min_y = max(0, min(y) - 5)
            max_x = min(w, max(x) + 5)
            max_y = min(h, max(y) + 5)
            text_parts.append([min_x, min_y, max_x, max_y])

            cv2.polylines(image_to_draw, [poly.reshape((-1, 1, 2))], True, color=(0, 0, 255), thickness=2)

        return image_to_draw, text_parts, time() - start


if __name__ == '__main__':
    craft = CRAFTWrapper(os.path.join("data", "craft-model", "craft_mlt_25k.pth"))
    image = cv2.imread(os.path.join("data", "images-to-test", "test-detector.jpg"))
    image_with_bbox, text_parts, t = craft.detect(image)
    cv2.imshow("Detected", image_with_bbox)
    for i, text in enumerate(text_parts):
        cv2.imwrite(f"{i}.jpg", image[text[1]:text[3], text[0]:text[2], :])
    key = cv2.waitKey(0)
    if key == 27:
        pass