# -*- coding: utf-8 -*-
"""
Created on Mon Aug 24 11:36:26 2020

@author: Peter Betlem
@institution: The University Centre in Svalbard
@year: 2020

The scripts below are improved from the approach used by Remote Sens. 2020, 
12(2), 330; https://doi.org/10.3390/rs12020330 and specifically tailored for the
digitisation of small hand samples and drill core models in a lightbox setting.

When using this script in conjunction with the automated marker detection, make
sure to run the marker detection first, followed by this script.
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

def extract_object(cfg_file, rename = True):
    """
    YML configuration file which specifies 
        photo_path: 
    Herein the first photo (alphab. listed) is the background frame, i.e., an
    image of the background scenery without any objects (including markers).
    
    !Please be advised that the code (currently) only works for a single dir. of
    images!
    
    Once done, the "rename" option (TRUE) toggles renaming of the original and
    processed data folders

    """
    print("!Please be advised that the code (currently) only works for a single dir. of images!")
    
    # read the YML configuration file with input
    # TODO: move rename parameter to cfg file
    cfg = read_yaml(cfg_file)
    
    # Scan through the photo_path dir and compile all accepted images
    a = glob.iglob(os.path.join(cfg["photo_path"],"**","*.*"))   #(([jJ][pP][gG])|([tT][iI][fF]))
    b = [path for path in a]
    photo_files = [x for x in b if (re.search("(.png$)|(.jpg$)|(.PNG$)|(.JPG$)",x))]
     
    
    # Make sure that there isn't another original media directory already,
    # abort if there is...
    if rename and pathlib.Path(pathlib.Path( \
                photo_files[0]).parent.parent,\
                "."+\
                pathlib.Path(photo_files[0]).parent.name+\
                "_original").exists():
        print("Backup dir already exists, check filestructure!")
        raise FileExistsError
    
    # Start using the openCV background removal magic
    # TODO: add toggable statement for use of different substractor modules
    fgbg = cv.createBackgroundSubtractorMOG2(detectShadows=False)
    
    
    for filename in photo_files:
        frame = cv.imread(filename)
        # learningRate = 0 implies that the algorithm is not updated on each
        # consecutive image; recommended but requires an "empty" scene image.
        fgmask = fgbg.apply(frame,learningRate = 0)
        
        if filename != photo_files[0]: # Because the first image is used for the background
            contours = cv.findContours(fgmask,cv.RETR_LIST, cv.CHAIN_APPROX_NONE)   
            contours = contours[0] if len(contours) == 2 else contours[1]
            contours = sorted(contours, key=cv.contourArea)    
            out_mask = np.zeros_like(frame)
            cv.drawContours(out_mask, [contours[-1]], -1, (255,255,255), cv.FILLED, 1)
            frame[out_mask == 0] = 255
            output_path = pathlib.Path(cfg["photo_path"],"processed",pathlib.Path(filename).name)
            output_path.parent.mkdir(parents=True,exist_ok=True)
            cv.imwrite(output_path.as_posix(),frame)
            
            #cv.imshow('ImageWindow', img)
            #cv.waitKey()
            

    # Rename the original media folders to be compatible with the Metashape scripts, but keep a backup!
    if rename:
        pathlib.Path(photo_files[0]).parent.rename(
            pathlib.Path(
                pathlib.Path(photo_files[0]).parent.parent,
                "."+pathlib.Path(photo_files[0]).parent.name+"_original"
                )
            )
        
        pathlib.Path(output_path).parent.rename(
            pathlib.Path(
                pathlib.Path(photo_files[0]).parent.parent,
                pathlib.Path(photo_files[0]).parent.name
                )
            )
    
if __name__ == "__main__":
    try:
        config_file = sys.argv[1]
    except:
        config_file = manual_config_file
        
    extract_object(config_file)

