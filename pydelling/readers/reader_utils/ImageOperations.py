import numpy as np
import cv2
from matplotlib import pyplot as plt


class ImageOperations:
    data: np.ndarray
    def get_polygons_from_image(self, min_vertices=4):
        # Finds closed polygons from the image
        # Convert numpy array to grayscale image
        cache_img = self.data.copy()
        print(cache_img.min())
        # transform to 0 255
        cache_img = cache_img - cache_img.min()
        print(cache_img)
        print(cache_img.min())
        cache_img = cache_img / cache_img.max()
        cache_img = cache_img * 255
        cache_img = cache_img.astype(np.uint8)
        print(cache_img)
        print(cache_img.mean())
        print(cache_img.max())
        print(cache_img.min())
        cache_img = cv2.cvtColor(cache_img, cv2.COLOR_BGR2GRAY)
        print(cache_img)


        edges = cv2.Canny(self.data, 100, 200)  # detect edges using Canny edge detection
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)  # find contours

        polygons = []
        for contour in contours:
            # approximate contour to a polygon
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            # Only keep polygons with more than a certain number of vertices
            if len(approx) >= min_vertices:
                polygons.append(approx)

        return polygons

    def plot_polygons(self, polygons):
        image_copy = self.data.copy()
        image_copy = cv2.cvtColor(image_copy, cv2.COLOR_GRAY2BGR)  # convert grayscale to BGR for visualization

        for polygon in polygons:
            cv2.polylines(image_copy, [polygon], True, (0, 255, 0), 2)  # draw polygon on the image

        plt.imshow(cv2.cvtColor(image_copy, cv2.COLOR_BGR2RGB))  # convert BGR to RGB for matplotlib
        plt.show()