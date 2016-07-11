#!/usr/bin/env python
# coding: utf-8
#
# Copyright © 2016 Dayong Wang <dayong.wangts@gmail.com>
#
# Distributed under terms of the MIT license.
from __future__ import print_function, division

DESCRIPTION = """
"""
import os
import sys
import argparse
import logging
from scipy.io import savemat
from deepfeat import get_extractor
import deepfeat.util as dutil
import openslide as osi
import skimage.io as skio
import numpy as np
from random import sample
from skimage.transform import resize
from scipy import sparse, io
import scipy.ndimage as nd

def create_parser():
    """ Parse program arguments.
    """
    parser = argparse.ArgumentParser(description=DESCRIPTION,
                                     formatter_class=
                                     argparse.RawTextHelpFormatter)
    parser.add_argument('extractor', type=str, help='name of extractor')
    parser.add_argument('conf_file', type=str, help='config file')
    parser.add_argument('feat_name', type=str, help='feature name')
    parser.add_argument('input_folder', type=str, help='output folder')
    parser.add_argument('wsi_list', type=str, help='wsi file')
    parser.add_argument('deep_model_level', type=int, help='deep model level')
    parser.add_argument('output_folder', type=str, help='output folder')

    parser.add_argument('--heatmap_level', type=int, default=2, help='the level of heatmap')
    parser.add_argument('--mask_image_level', type=int, default=5, help='mask image level')
    parser.add_argument('--augmentation', type=int, default=1, help='do rotation')
    parser.add_argument('--window_size', type=int, default=256, help='windows size')
    parser.add_argument('--batch_size', type=int, default=100, help='batch size')
    parser.add_argument('--group_size', type=int, default=100, help='group size')
    parser.add_argument('--step_size', type=int, default=100, help='step size')
    parser.add_argument('--device_ids', nargs='+', type=int, default=[0],
                        help='config file')
    parser.add_argument('--gpu', action='store_true',
                        help='config file')
    parser.add_argument("--log", type=str, default="INFO", help="log level")

    return parser

def save_sparse_matrix(outputName, data):
    m = sparse.csr_matrix(data)
    io.mmwrite(outputName, m)

def load_sparse_matrix(inputName):
    newm = io.mmread(inputName)
    return newm.toarray()

#
# split list into groups
#
def list_split(l, n):
    return [ l[i:i+n] for i in range(0, len(l), n) ]

def gen_heatmap_wsi(extractor, feat_name, wsiName, mask_image, mask_image_level, deep_model_level, heatmap_level, window_size, augmentation, batch_size = 100, group_size = 100, step_size = 128):
    def extend_inds_to_level0(input_level, h, w):
        gap = input_level - 0
        v = np.power(2, gap)
        hlist = h * v + np.arange(v)
        wlist = w * v + np.arange(v)
        hw = []
        for hv in hlist:
            for wv in wlist:
                hw.append([hv, wv])
        return hw
    def get_tl_pts_in_level0(outputLevel, h_level0, w_level0, window_size):
        scale = np.power(2, outputLevel)
        window_size_level0 = window_size * scale
        window_size_level0_half = window_size_level0 / 2

        h1_level0, w1_level0 = h_level0 - window_size_level0_half, w_level0 - window_size_level0_half
        return int(h1_level0), int(w1_level0)
    def get_image_level0(wsi, h1_level0, w1_level0, outputLevel, window_size):
        img = wsi.read_region(
                (w1_level0, h1_level0),
                outputLevel, (window_size, window_size))
        img = np.asarray(img)[:,:,:3]
        return img
    #
    # data augmentation
    #
    def image_augmentation(img_000):
        if augmentation == 1:
            return [img_000]
        elif augmentation == 6:
            img_090 = nd.rotate(img_000, 90)
            img_180 = nd.rotate(img_090, 180)
            img_270 = nd.rotate(img_180, 270)
            img_fph = np.fliplr(img_000)
            img_fpv = np.flipud(img_000)
            return [img_000, img_090, img_180, img_270, img_fph, img_fpv]
        else:
            return None
    #
    # extract image patches from WSI on LEVEL_0 using the
    #
    def get_image(wsi, h1_ml, w1_ml):
        h1_ml_2_level0 = h1_ml * np.power(2, deep_model_level)
        w1_ml_2_level0 = w1_ml * np.power(2, deep_model_level)
        img = wsi.read_region(
                (w1_ml_2_level0, h1_ml_2_level0),
                deep_model_level,
                (window_size, window_size)
                )
        img = np.asarray(img)[:,:,:3]
        imgs = image_augmentation(img)
        return imgs
    #
    # check the overlapping with tissue segmentation, which is helpful to reduce
    # the number of pataches
    #
    def has_overlapping_with_tissue_using_mask(msk, h1_ml, w1_ml, gap_between_mask_model):
        if msk is None:
            return True
        else:
            h1_kl = int(h1_ml / np.power(2, gap_between_mask_model))
            w1_kl = int(w1_ml / np.power(2, gap_between_mask_model))
            window_size_kl = int(window_size / np.power(2, gap_between_mask_model))
            return np.sum(msk[h1_kl:h1_kl + window_size_kl, w1_kl:w1_kl + window_size_kl]) > 0
    #
    # Get prediction results using DL
    # len(v_img) = augmentation * num_patches
    #
    def doExtraction(v_img, batch_size):
        values_list = []
        v_img_list = list_split(v_img, batch_size)
        values = []
        for i, v_img_i in enumerate(v_img_list):
            logging.info("\t\t\t sub-group %d (%d)"%(i, len(v_img_i)))
            values_i = extractor.batch_extract_numpy(v_img_i, [feat_name])
            values_i = values_i[0] # get the first feature group
            values_i = values_i[:, 1].reshape(-1) # get the possibility of positive
            values_i[values_i<1e-4] = 0.0
            values = np.concatenate((values, values_i))
        values = values.reshape(-1, augmentation) # numpy is row first
        values_m = np.mean(values, axis=1)
        values_m = values_m.reshape(-1)
        return values_m

    def gen_heatmap_batch(wsi, msk, outputName):
        # ml -> model level 0, 1, 2, 3, 4, 5
        # kl -> mask level 5
        # hl -> heatmap level 2
        img_w_ml, img_h_ml = wsi.level_dimensions[deep_model_level]
        img_w_hl, img_h_hl = wsi.level_dimensions[heatmap_level]
        heatmap = np.zeros((img_h_hl, img_w_hl, 2))

        # generate all the patches locations
        inds_list = []
        for h1_ml in range(0, img_h_ml, step_size):
            for w1_ml in range(0, img_w_ml, step_size):
                if h1_ml + window_size > img_h_ml:
                    h1_ml = img_h_ml - window_size
                if w1_ml + window_size > img_w_ml:
                    w1_ml = img_w_ml - window_size
                if has_overlapping_with_tissue_using_mask(msk, h1_ml, w1_ml, mask_image_level - deep_model_level):
                    inds_list.append([h1_ml, w1_ml])
        logging.info("\t There are %d patches in total!"%(len(inds_list)))

        # predict batches
        values = np.zeros((len(inds_list),), np.float32)
        inds_list_group = list_split(inds_list, group_size)
        for i, inds_list_group_i in enumerate(inds_list_group):
            v_img = []
            for h1_ml, w1_ml in inds_list_group_i:
                imgs = get_image(wsi, h1_ml, w1_ml)
                v_img += imgs
            logging.info("\t\t Processing: group %d:%d (%d) : %s"%(i, len(v_img), len(inds_list_group), wsiName))
            values_i = doExtraction(v_img, batch_size)
            #values_list.append(values_i)
            values[i*group_size:i*group_size + len(inds_list_group_i)] = values_i
            #break
        #values = np.hstack(values_list)
        logging.info("\t Done!")

        # genearte the heatmap
        if 1:
            logging.info("\t Updating heatmap...")
            for (h1_ml, w1_ml), v in zip(inds_list, values):
                h1_hl = int(h1_ml / np.power(2, heatmap_level - deep_model_level))
                w1_hl = int(w1_ml / np.power(2, heatmap_level - deep_model_level))
                window_size_hl = int(window_size / np.power(2, heatmap_level - deep_model_level))

                ori_patch = heatmap[h1_hl:h1_hl+window_size_hl, w1_hl:w1_hl+window_size_hl, :]
                l1, c1 = np.split(ori_patch, 2, axis=2)

                nmask = np.tile(np.array([v, 1]).reshape((1,1,2)), (window_size_hl, window_size_hl, 1))
                l2, c2 = np.split(nmask, 2, axis=2)

                ## merging
                c3 = c1 + c2
                l3 = ((l1 * c1) + l2) / c3
                heatmap[h1_hl:h1_hl+window_size_hl, w1_hl:w1_hl+window_size_hl, :] = np.dstack((l3, c3))
            logging.info("\t Done!")

        # Save the results
        if 1:
            logging.info("\t Saving Mask...")
            ## save the npy file ##
            heatmap = np.squeeze(heatmap[:,:,0]).astype(np.float32)
            heatmap[heatmap<1e-5] = 0.0
            #np.save(outputName + ".npy", heatmap)

            ## save the heat map ##
            img_h_kl = img_h_hl / np.power(2, mask_image_level - heatmap_level)
            img_w_kl = img_w_hl / np.power(2, mask_image_level - heatmap_level)
            heatmap_kl = (resize(heatmap, (img_h_kl, img_w_kl)) * 255).astype(np.uint)
            skio.imsave(outputName, heatmap_kl)
        # end of function : gen_heatmap_batch

    ## begin of function : gen_heatmap_wsi ##
    logging.info("Processing: %s ..." % (wsiName))
    wsi = osi.open_slide(wsiName)
    if mask_image:
        msk = skio.imread(mask_image, True)
    else:
        msk = None
    outputName = '%s/%s'%(args.output_folder, wsiName.split('/')[-1].split('.')[0] + '.png')
    if not os.path.exists(outputName):
        gen_heatmap_batch(wsi, msk, outputName)
    else:
        logging.info("Omit : %s"%(outputName))

def main(args):
    """ Main entry.
    """
    logging.info("Creating extractor ...")
    extractor = get_extractor(
        args.extractor, args.conf_file,
        {
            'use_gpu': args.gpu,
            'device_id': args.device_ids[0],
        })
    logging.info("\tDone!")

    if extractor is not None:
        lines = [l.strip().split(' ') for l in open(args.wsi_list) if l[0] != '#']
        heatmap_level = max(args.deep_model_level, args.heatmap_level)
        for l in lines:
            if len(l) > 1:
                wsi, msk_image = ['%s/%s'%(args.input_folder, v) for v in l]
                gen_heatmap_wsi(extractor, args.feat_name, wsi, msk_image,
                    args.mask_image_level, args.deep_model_level, heatmap_level, args.window_size, args.augmentation, args.batch_size, args.group_size, args.step_size)
            else:
                wsi = '%s/%s'%(args.input_folder, l[0])
                gen_heatmap_wsi(extractor, args.feat_name, wsi, None,
                    args.mask_image_level, args.deep_model_level, heatmap_level, args.window_size, args.augmentation, args.batch_size, args.group_size, args.step_size)

if __name__ == '__main__':
    args = create_parser().parse_args()
    
    # set up loggging -- 
    #   logging levels are defined as strings (uppercase)
    numeric_level = getattr(logging, args.log.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError("Invalid log level: " + args.log)

    logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                        level=numeric_level)

    # execute main with all arguments
    main(args)