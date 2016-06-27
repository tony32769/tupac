'''
XX -- not started
IP -- in progress
OK -- done

Step 1 (OK): remove small objects
Step 2 (OK): count the number of large objects
Step 3 (OK): get properties of each large object (sklearn labeled)
Step 4 (OK): within each large object, get a random point and define a patch
Step 5 (OK): save the extracted patch (more for larger regions via sklearn regionprops)

'''

import random
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from skimage import data
from skimage.filters import threshold_otsu
from skimage.segmentation import clear_border
from skimage.measure import label
from skimage.morphology import closing, square
from skimage.measure import regionprops
from skimage.color import label2rgb
from skimage.io import *
from sklearn.feature_extraction.image import extract_patches_2d

import cv2
import openslide as osi

levelpow = 4

def extend_inds_to_level0(input_level, h, w):
    gap = input_level - 0
    v = np.power(levelpow, gap)
    hlist = h * v + np.arange(v)
    wlist = w * v + np.arange(v)
    hw = []
    for hv in hlist:
        for wv in wlist:
            hw.append([hv, wv])
    return hw

def get_tl_pts_in_level0(OUT_LEVEL, h_level0, w_level0, wsize):
    scale = np.power(levelpow, OUT_LEVEL)
    wsize_level0 = wsize * scale
    wsize_level0_half = wsize_level0 / 2

    h1_level0, w1_level0 = h_level0 - wsize_level0_half, w_level0 - wsize_level0_half
    return int(h1_level0), int(w1_level0)

def get_image(wsi, h1_level0, w1_level0, OUT_LEVEL, wsize):
    img = wsi.read_region(
            (w1_level0, h1_level0),
            OUT_LEVEL, (wsize, wsize))
    img = np.asarray(img)[:,:,:3]
    return img

def extract_patches(image_number, # A STRING
                    n_patches = 10,
                    area_threshold = 1500,
                    patch_size = 1000,
                    input_level = 2,
                    output_level = 0,
                    output_directory = "patches", # ALWAYS change this default
                    interactive = True):

    image = imread('/data/dywang/Database/Proliferation/libs/stage03_deepFeatMaps/results/roi-level1_06-24-16/thresholded-0.85/TUPAC-TR-' + image_number + '.png')
    wsi = osi.open_slide('/data/dywang/Database/Proliferation/data/TrainingData/training_image_data/TUPAC-TR-' + image_number + '.svs')

    print "Loaded " + image_number
### STAGE 1: PREPROCESSING

    cleared = image.copy()
    clear_border(cleared)

    # label image regions
    label_image = label(cleared)
    borders = np.logical_xor(image, cleared)
    label_image[borders] = -1

    if interactive:
        image_label_overlay = label2rgb(label_image, image=image)
        fig, ax = plt.subplots(ncols=1, nrows=1, figsize=(6, 6))
        ax.imshow(image_label_overlay)

### STAGE 2: FIRST PASS FOR REGION ELIMINATION & METRICS
    A = []
    final_regions = []

    for region in regionprops(label_image):
        if region.area < area_threshold:
            continue

        A.append(region.area)
        final_regions.append(region)

        if interactive:
            minr, minc, maxr, maxc = region.bbox
            rect = mpatches.Rectangle((minc, minr), maxc - minc, maxr - minr,fill=False, edgecolor='red', linewidth=2)
            ax.add_patch(rect)

    if interactive:
        plt.show()

    tot_area = sum(A)
    # K is the number of patches
    K = n_patches
    final_regions.sort(key=lambda x: x.area)

### STAGE 3: SECOND PASS FOR (SELECTED) REGION PATCH EXTRACTION
    n_remaining = K
    for i, region in enumerate(final_regions):
        to_extract = 0 # initialize

        if i == len(final_regions)-1:
            # largest object
            to_extract = n_remaining # if there are too few otherwise, catch them here

        else:
            # these are sorted -- start with the smallest patch
            to_extract = int( K * (float(region.area) / tot_area) )
            if to_extract == 0:
                to_extract = 1

            n_remaining -= to_extract

        print region.area, to_extract

        centers = []

        if to_extract == 1: # in this case, let's take the centroid
            centers = [region.centroid]

        else:
            points = region.coords
            centers = random.sample(points, to_extract)

        for centroid in centers:
            # each centroid is a tuple
            indices = extend_inds_to_level0(input_level, centroid[0], centroid[1])

            idx = int(len(indices) / 2)
            chcw_level0 = indices[idx] # take middle point (this is basically the centroid at level 0)
            h_level0, w_level0 = chcw_level0
            h1_level0, w1_level0 = get_tl_pts_in_level0(output_level,
                                                        h_level0,
                                                        w_level0,
                                                        patch_size) # should give top left corner of patch

            img = get_image(wsi, h1_level0, w1_level0, output_level, patch_size)

            img_name = output_directory + "/TUPAC-TR-" + image_number + "-(" + str(h1_level0) + "," + str(w1_level0) + ").png"
            imsave(img_name, img)
            print "\t => " + img_name


####

from os import listdir
from os.path import isfile, join

save_directory = "patches_06-27-16"
image_numbers = ["{0:0>3}".format(n) for n in xrange(500)]

count = 0
for num in image_numbers:
    try:
        extract_patches(num,output_directory=save_directory, interactive=False)
        count += 1
    except Exception as e:
        print e
        print "[!] " + num + " does not exist"

print "[X] Done, count is " + str(count)

###

# extract_patches('039', interactive=False)
