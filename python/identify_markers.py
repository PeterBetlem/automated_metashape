# -*- coding: utf-8 -*-
"""
@author: Peter Betlem
@institution: University Centre in Svalbard, Svalbard
@year: 2020

"""

# import standard libs
import os
import sys
from pathlib import Path, PurePath
import glob
import re

# import calc and image libs
import numpy as np
import cv2
from cv2 import aruco
import pandas as pd

# import multiprocessing libs
import multiprocessing as mp

## Load custom modules and config file: slightly different depending whether running interactively or via command line
import read_yaml

class marker_detection():
    """
    Class used for the detection of ArUcO markers from photos. Configuration 
    file setup (YML) is shared with the metashapw_workflow_functions to allow
    for interoperability.
    """
    def __init__(self, cfg):
        
        # Internalise configuration to class
        self.cfg = cfg
        
        # create output file dir for gcps, if not existing
        self.output_file = Path(
            self.cfg["photo_path"],"gcps","prepared","gcp_imagecoords_table.csv"
            )
        _check_output_path(self.cfg["photo_path"])
        
        print(f"Accessing and analysing photos @ {self.cfg['photo_path']}")
        
        self.process_images()
        
    def process_images(self):
        """
        Processing all images found in the photo_path dir specified by the YML
        configuration file. To speed things up, this step uses parallel processing

        """
        
        # Search all images
        a = glob.iglob(os.path.join(self.cfg["photo_path"],"**","*.*"))   #(([jJ][pP][gG])|([tT][iI][fF]))
        b = [path for path in a]
        photo_files = [x for x in b if (re.search("(.tif$)|(.jpg$)|(.TIF$)|(.JPG$)",x) and (not re.search("dem_usgs.tif",x)))]
        
        print(f"Found {len(photo_files)} images for processing.")        
        print("Starting multiprocessing...")
        # Start multiprocessing on all found images
        pool = mp.Pool(mp.cpu_count())
        
        combined = [pool.apply(
            _assign_marker_coordinates_on_image,
            args = (x,
                    self.cfg["detectGCPs"]["aruco_dict"],
                    self.cfg["detectGCPs"]["corner"])
            ) for x in photo_files]
        
        pool.close() 
        
        print("Finalised multiprocessing...")
        # drop all None entries
        combined = list(filter(None.__ne__,combined))
        
        # Combine pixel coordinate lists into single dataframe (if not empty)
        try:
            self.image_markers = pd.concat(combined)
        except:
            print("No GCPs identified in image pool...")
            raise
            
        self.image_markers["filename"] = self.image_markers["filename"].apply(lambda x: os.path.join(
            os.path.basename(os.path.dirname(x)),
            os.path.basename(x)
            ).replace("\\","/"))
        self.image_markers.to_csv(self.output_file, mode = 'w', header = False, index = False, sep = ',')
        print(f'Exported pixel coordinates to {PurePath(self.cfg["photo_path"],"gcps","prepared")} folder.')
           
def _assign_marker_coordinates_on_image(filename,aruco_dict,corner=None):
    """
    Standalone script for the identification of ArUcO markers in an image 
    (filename). The specified aruco_dict is cross-chcked vs those found in the 
    opencv specifications. The corner parameter specifies which corner of the
    marker is reported back.   

    """
    
    # opencv magic
    frame = cv2.imread(filename)
    parameters =  aruco.DetectorParameters_create()
    corners, ids, rejectedImgPoints = aruco.detectMarkers(
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),                                           
        aruco.Dictionary_get(aruco_dict),                                   
        parameters=parameters
        )
    
    # compiling all corners into np array
    corners2 = np.array([c[0] for c in corners])
    
    if isinstance(ids, (np.ndarray, np.generic) ):
        # and then into a pd DataFrame    
        data = pd.DataFrame(
            {"x": corners2[:,:,0].flatten(), 
            "y": corners2[:,:,1].flatten()},
            index = pd.MultiIndex.from_product(
                [ids.flatten(), ["c{0}".format(i )for i in np.arange(4)+1]],
                names = ["marker", ""] 
                )
            )
        
        # calculating the centre
        data = data.unstack().swaplevel(0, 1, axis = 1).stack()
        data["m1"] = data[["c1", "c2"]].mean(axis = 1)
        data["m2"] = data[["c2", "c3"]].mean(axis = 1)
        data["m3"] = data[["c3", "c4"]].mean(axis = 1)
        data["m4"] = data[["c4", "c1"]].mean(axis = 1)
        data["centre"] = data[["m1", "m2", "m3", "m4"]].mean(axis = 1)
        data = data.reset_index()
        
        # specifying the corner for which the pixel coords are reported
        if corner == "bottomleft": # as defined by the OpenCV Aruco Library
            x_data = data[data['level_1']=='x'].c1.values
            y_data = data[data['level_1']=='y'].c1.values
        elif corner == "topleft":
            x_data = data[data['level_1']=='x'].c2.values
            y_data = data[data['level_1']=='y'].c2.values
        elif corner == "topright":
            x_data = data[data['level_1']=='x'].c3.values
            y_data = data[data['level_1']=='y'].c3.values
        elif corner == "bottomright":
            x_data = data[data['level_1']=='x'].c4.values
            y_data = data[data['level_1']=='y'].c4.values
        else:
            x_data = data[data['level_1']=='x'].centre.values
            y_data = data[data['level_1']=='y'].centre.values
            
        df = pd.DataFrame(
            {
                'marker':data[data['level_1']=='x'].marker.values,
                'filename':filename,
                'x':x_data,
                'y':y_data
                }
            )
        return df
    else:
        return None
    
def _check_output_path(photo_path):    
    output_dir = Path(
            photo_path,"gcps","prepared"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    
class real_world_positions():
    """
    Class used to derive real world coordinates and store them as a csv. Takes
    either a pre-generated 2D template image with known dimensions, or requires
    a geopackage with specific formatting.
    """
    def __init__(self, cfg):
        
        # internalise config data
        self.cfg = cfg
               
        # create output dir if not existing
        self.output_file = Path(
            self.cfg["photo_path"],"gcps","prepared","gcp_table.csv"
            )
        _check_output_path(self.cfg["photo_path"])
        
        # automatically run either of two functions based on YML file
        if self.cfg["detectGCPs"]["template"]["enabled"]:
            print("Implementing real world positions from 2D template file.")
            self.real_world_positions_from_2D_template()
        else:
            print("Implementing real world positions from geopackage file.")
            self.real_world_positions_from_gpkg()
            
            
    def real_world_positions_from_2D_template(self):
        """
        This function is used e.g. when doing close range photogrammetry of 
        core and small hand samples. It relies on a predesigned ground control
        point sheet for which the absolute dimensions of the figure are known.
        The GCP locations can then be dynamically calculated after analysis of
        the GCP sheet.
        
        This method was used in e.g. 
        Remote Sens. 2020, 12(2), 330; https://doi.org/10.3390/rs12020330
        """
        
        # aruco magic
        frame = cv2.imread(self.cfg["detectGCPs"]["template"]["template_file_path"].as_posix())
        self.image_markers = _assign_marker_coordinates_on_image(
            self.cfg["detectGCPs"]["template"]["template_file_path"].as_posix(),
            self.cfg["detectGCPs"]["aruco_dict"]
            )
        
        # transforming pixel values to real world distances based on known
        # template dimensions.
        self.image_markers.x *= self.cfg["detectGCPs"]["template"]["template_size"]/np.shape(frame)[0] 
        self.image_markers.y *= self.cfg["detectGCPs"]["template"]["template_size"]/np.shape(frame)[0]
        self.image_markers['z'] = 0
        
        # stores marker real world positions in gcp_table file.
        self.image_markers[['marker','x','y','z']].to_csv(self.output_file, mode='w', header=False,index=False,sep=',')
        
        print(f'Exported real world marker coordinates to {PurePath(self.cfg["photo_path"],"gcps","prepared")} folder.')
        
    def real_world_positions_from_gpkg(self):
        print("This function has yet to be implemented...")
        print("Nothing will be outputted. Please format your own marker data according to the template.")
        
        
if __name__ == "__main__":
    
    try:  # running interactively
        config_file = sys.argv[1]
    except:  # running from command line
        config_file = "../config/identify_markers_config.yml"
        
    cfg = read_yaml.read_yaml(config_file)
    if "detectGCPs" in cfg and cfg["detectGCPs"]["enabled"]:
        B = real_world_positions(cfg)
        A = marker_detection(cfg)
    else:
        print("Skipping GCP coordinate generation. Check your config. file if this is unwanted behaviour.")
