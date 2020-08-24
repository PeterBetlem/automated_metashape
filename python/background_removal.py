# -*- coding: utf-8 -*-
"""
Created on Mon Aug 24 11:36:26 2020

@author: Peter Betlem
@institution: The University Centre in Svalbard
@year: 2020

The scripts below are improved from the approach used by Remote Sens. 2020, 
12(2), 330; https://doi.org/10.3390/rs12020330 and specifically tailored for the
digitisation of small hand samples and drill core models in a lightbox setting.

"""

# Import standard scripts
import sys
import os
import pathlib
import re
import glob

# import calc libs
import numpy as np
import cv2 as cv

# Import custom libs
from read_yaml import read_yaml

manual_config_file = "../config/background_removal_config.yml"

def extract_object(cfg_file):
    """
    YML configuration file which specifies 
        photo_path: 
    Herein the first photo (alphab. listed) is the background frame, i.e., an
    image of the background scenery without any objects (including markers).

    """
    cfg = read_yaml(cfg_file)
    
    a = glob.iglob(os.path.join(cfg["photo_path"],"**","*.*"))   #(([jJ][pP][gG])|([tT][iI][fF]))
    b = [path for path in a]
    photo_files = [x for x in b if (re.search("(.png$)|(.jpg$)|(.PNG$)|(.JPG$)",x))]
     
    fgbg = cv.createBackgroundSubtractorMOG2(detectShadows=False)
    
    for filename in photo_files:
        frame = cv.imread(filename)
        fgmask = fgbg.apply(frame,learningRate = 0)
        
        if filename != photo_files[0]: # Because the first image is used for the background
            contours = cv.findContours(fgmask,cv.RETR_LIST, cv.CHAIN_APPROX_NONE)   
            contours = contours[0] if len(contours) == 2 else contours[1]
            contours = sorted(contours, key=cv.contourArea)    
            out_mask = np.zeros_like(frame)
            cv.drawContours(out_mask, [contours[-1]], -1, (255,255,255), cv.FILLED, 1)
            frame[out_mask == 0] = 255
            output_path = str(pathlib.Path(cfg["photo_path"],"processed",pathlib.Path(filename).name))
            cv.imwrite(output_path,frame)

if __name__ == "__main__":
    try:
        config_file = sys.argv[1]
    except:
        config_file = manual_config_file
        
    extract_object(config_file)

