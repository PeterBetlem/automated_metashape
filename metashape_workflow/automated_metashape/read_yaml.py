# -*- coding: utf-8 -*-
"""
Created on Mon Aug 24 11:49:29 2020

@author: Peter Betlem
@institution: The University Centre in Svalbard
@year: 2020
"""

# import standard libs
import sys
import os

# import specialised libs
import yaml
import pathlib
import Metashape

try:
    from cv2 import aruco
except:
    print("Unable to load OpenCV2 aruco libraries.")
    pass

"""
Based on UCDavis work, see https://github.com/ucdavis/metashape,
Part below based on https://stackoverflow.com/a/25896596/237354

"""

def convert_paths_and_commands(a_dict):
    for k, v in a_dict.items():
        if not isinstance(v, dict):
            if isinstance(v, str):
                if v and ('path' in k):    # all paths that are supplied in the config file are automatically converted to Path type
                    a_dict[k] = pathlib.Path(v)
                elif v and ('Metashape' in v or 'aruco' in v) and not ('path' in k) and not ('project' in k): # for Metashape compatibility
                    a_dict[k] = eval(v)
            elif isinstance(v, list):
                a_dict[k] =  [eval(item) for item in v if("Metashape" in item)]
        else:
            a_dict[k] = convert_paths_and_commands(v)
    return a_dict


def read_yaml(yml_path):
    yml_path = pathlib.Path(yml_path)
    with open(yml_path,'r') as ymlfile:
        cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
         
    return convert_paths_and_commands(cfg)
