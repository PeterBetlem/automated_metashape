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

def convert_paths(a_dict):
    for k, v in a_dict.items():
        if not isinstance(v, dict):
            if isinstance(v, str):
                if v and ('path' in k):    # all paths that are supplied in the config file are automatically converted to Path type
                    a_dict[k] = pathlib.Path(v)
        else:
            a_dict[k] = convert_paths(v)
    return a_dict

def read_yaml(yml_path):
    yml_path = pathlib.Path(yml_path)
    with open(yml_path,'r') as ymlfile:
        cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
        
    cfg = convert_paths(cfg)

    return cfg
