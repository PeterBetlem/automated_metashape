# -*- coding: utf-8 -*-
"""
@author: Peter Betlem
@institution: University Centre in Svalbard, Svalbard
@year: 2020

The following classes are inspired by the UC Davis work, which in full
is documented here: https://github.com/ucdavis/metashape.
"""
# Import libraries

# import standard libs
import os
import sys
from pathlib import Path
import datetime
import glob
import re
import logging
from logging.config import dictConfig
import yaml
import numpy as np
import pandas as pd
from shutil import copyfile

import keyring, getpass

# import the Metashape functionality
import Metashape

# import custom scripts
import read_yaml

def stamp_time(): #  - thank you UCDavis!
    '''
    Format the timestamps as needed
    '''
    stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M')
    return stamp

# Used by add_gcps function - thank you UCDavis!
def _get_marker(chunk, label):
    for marker in chunk.markers:
        if marker.label == label:
            return marker
    return None

# Used by add_gcps function - thank you UCDavis!
def _get_camera(chunk, label):
    for camera in chunk.cameras:
        if camera.label.lower() == label.lower():
            return camera
    return None          

def _webhook(service,get=True):
    '''
    :param service: Name of the service for which a password has been stored
    :param username: Username for the service specified above
    :return: webhook url for the username specified above, if None, prompts the user to specify the password
    '''
    if get == True:
        if keyring.get_password(service, "system") is None:
            keyring.set_password(service, "system", getpass.getpass())
        return keyring.get_password(service, "system")
    else:
        keyring.set_password(service, "system", getpass.getpass())
        
def _msteams_connector(task,**kwargs):
        try:
            import pymsteams
            msteams = pymsteams.connectorcard(_webhook("msteams_metashape_channel"))
            
            if task != "aborted" and kwargs["run_id"]:
                message = f'{task}ed stand-alone processing of Agisoft Metashape runtime-id {kwargs["run_id"]} on terminal {os.environ["COMPUTERNAME"]}.'
            elif task == "aborted":
                message = f'Stand-alone processing of Agisoft Metashape on terminal {os.environ["COMPUTERNAME"]} aborted.'
            
            msteams.text(message)
            msteams.send()
        except:
            logger.warning("Failed to import/operate pymsteams.")
            pass
            
            
# Main functions
class MetashapeProcessing:

    def _about(self):
        self.__version__ = "2020-dec-02"
        self.__author__ = "Peter Betlem"
        self.__institution__ = "The University Centre in Svalbard"
        self.__license__ = "BSD 3-Clause License"
        self.__copyright__ = "(c) 2020, Peter Betlem"
        
    def __init__(self, config_file, logger=logging.getLogger(__name__)):
        
        self.logger = logger
        self._about()
        
        self.cfg = read_yaml.read_yaml(config_file)
        self.config_file = config_file
        
        if not self.cfg["output_path"].exists():
            self.cfg["output_path"].mkdir(parents=True)
        if not self.cfg["project_path"].exists():
            self.cfg["project_path"].mkdir(parents=True)
            
        self.run_name = self.cfg["run_name"]
        self.run_id = "_".join([self.run_name,stamp_time()])
        self.project_file = Path(
            self.cfg["project_path"], 
            '.'.join([self.run_id, 'psx']) 
            )
        
        self._init_logging()
        self._check_environment()
        self._init_metashape_document()
        
        if "networkProcessing" in self.cfg and self.cfg["networkProcessing"]["enabled"]:
            self._init_network_processing()
            self.network = True
            self.logger.info('Network mode activated.')
            self._return_parameters(stage="networkProcessing") 
        else:
            self.network = False
        
        self.init_tasks()
        
        self._terminate_logging()

    def _init_logging(self):
        # TODO: add configuration to the YML file
        
        log_dict = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'standard': {
                    'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
                },
            },
            'handlers': {
                'default': {
                    'level': 'INFO',
                    'formatter': 'standard',
                    'class': 'logging.StreamHandler',
                },
                'file_handler': {
                    'level': 'INFO',
                    'filename': Path(self.cfg["output_path"],self.run_id+'.log'),
                    'class': 'logging.FileHandler',
                    'formatter': 'standard'
                }
            },
            'loggers': {
                '': {
                    'handlers': ['file_handler','default'],
                    'level': 'INFO',
                    'propagate': True
                },
            }
        }
    
        dictConfig(log_dict)
        
        if self.cfg["load_project_path"]:
            copyfile(self.cfg["load_project_path"].with_suffix('.log'),
                  Path(self.cfg["output_path"],self.run_id+'.log')
                )
           
            self.logger.info('--------------')
            self.logger.info('Continued run initiated.')
        else:
            self.logger.info('--------------')
            self.logger.info('Fresh run initiated.')
        self.logger.info(f'Runtime id: {self.run_id}')
        self.logger.info('--------------')

        self.logger.info(f'Agisoft Metashape Professional Version: {Metashape.app.version}.')
        self.logger.info(f'Python package version: {self.__version__}.\n')
        _msteams_connector(task = "Start", run_id = self.run_id)

        # open run configuration again. We can't just use the existing cfg file because its objects had already been converted to Metashape objects (they don't write well)
        # with open(self.config_file) as file:
        #     config_full = yaml.load(file, Loader=yaml.SafeLoader)
        # self.logger.info('\n### Start of configuration file ###\n'+\
        #                  yaml.dump(config_full, default_flow_style=False)+\
        #                 '### End of configuration file ###\n')
        #self._log_parameters()    
        #self.logger.info('')
        
    def _return_parameters(self,stage=None,log=None):
        with open(self.config_file) as file:
            config_full = yaml.load(file, Loader=yaml.SafeLoader)
        
        if not stage:
            config_dump = {k: v for k, v in config_full.items() if not isinstance(config_full[k],dict)}
            stage = "startup"
        else:
            config_dump = {k: v for k, v in config_full.items() if k == stage}
        
        parameters = f'\n\n### Start of input file configuration for {stage}-stage ###\n'+\
                         yaml.dump(config_dump, default_flow_style=False)+\
                         f'### End of input file configuration for {stage}-stage ###\n'
        if log:
            self.logger.info(parameters)
        else:
            return parameters
        
    def _terminate_logging(self):
        self.logger.info('--------------')
        self.logger.info('Run completed.')
        self.logger.info('--------------\n')
        _msteams_connector(task = "Finish", run_id = self.run_id)
        
    def _check_environment(self):
        if "onedrive" in str(self.cfg["load_project_path"]).lower():
            self.logger.error("Detected OneDrive folder for project - background fileupdating causes instability. Terminating...")
            raise
        
  
    def _init_metashape_document(self):
        self.doc = Metashape.Document()
        self.doc.read_only = False
        
        if self.cfg["load_project_path"]:
            self.doc.open(self.cfg["load_project_path"].resolve().with_suffix('.psx').as_posix())
            self.logger.info(f'Loaded existing project {self.cfg["load_project_path"]}')
        else:
            # Initialize a chunk, set its CRS as specified
            self.logger.info(f'Creating new project {self.cfg["load_project_path"]}')
            self.chunk = self.doc.addChunk()
            self.chunk.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])
            self.chunk.marker_crs = Metashape.CoordinateSystem(self.cfg["addGCPs"]["gcp_crs"])
        
        # Save doc doc as new project (even if we opened an existing project, save as a separate one so the existing project remains accessible in its original state)
        self.doc.save(str(self.project_file))
        self.logger.info(f'Saved project as {str(self.project_file)}'+self._return_parameters())
        
    def _init_network_processing(self):
        try:
            self.client = Metashape.NetworkClient()
            self.client.connect(self.cfg["networkProcessing"]["server_ip"])
            self.logger.info(f'Connected to network @ {self.cfg["networkProcessing"]["server_ip"]} running Metashape version {self.client.serverInfo()["version"]}.')
            self.task_batch = list()
        except (RuntimeError,NameError):
            raise
    
    def init_tasks(self):
        """
        Cycling through the entire predefined workflow. In this case the workflow
        is adjusted to that used at the University Centre in Svalbard.
        """
        
        # TODO: Add all other processing step options here as well
        
        if "addPhotos" in self.cfg and self.cfg["addPhotos"]["enabled"]:
            self.add_photos()
        
        if "addGCPs" in self.cfg and self.cfg["addGCPs"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["addGCPs"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.add_gcps() # call to original metashape_workflow_functions
            
        if "alignPhotos" in self.cfg and self.cfg["alignPhotos"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["alignPhotos"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.align_photos()
        
        if "optimizeCameras" in self.cfg and self.cfg["optimizeCameras"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["optimizeCameras"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.optimize_cameras()
        
        if "buildDenseCloud" in self.cfg and self.cfg["buildDenseCloud"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildDenseCloud"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_dense_cloud()
            
        if "filterDenseCloud" in self.cfg and self.cfg["filterDenseCloud"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["filterDenseCloud"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.filter_dense_cloud()
            
        if "buildMesh" in self.cfg and self.cfg["buildMesh"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildMesh"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_mesh()
            
        if "buildTexture" in self.cfg and self.cfg["buildTexture"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildTexture"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_texture()
            
        if "buildTiledModel" in self.cfg and self.cfg["buildTiledModel"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildTiledModel"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_tiled_model()
            
        if "buildDEM" in self.cfg and self.cfg["buildDEM"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildDEM"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_dem()
            
        self.export_report()
        
        if self.network:
            self._network_submit_batch()
            
        del self.doc
            
    def _encode_task(self, task):
        """
        All tasks need to be encoded before submission to the Agisoft Metashape Network.
        This also includes passing along all the chunks that need processing.
        """
        
        encoded_task = Metashape.NetworkTask()
        encoded_task.name = task.name
        encoded_task.params = task.encode()
        for c in self.doc.chunks:
            encoded_task.frames.append((c.key,0))
        self.task_batch.append( encoded_task )
    
    def add_photos(self):
        
        # TODO: provide dictionary check to add_photos as per the other functions
        self.logger.info('Initiating add_photos step...')
        a = glob.iglob(str(Path(self.cfg["photo_path"],"**","*.*")))   #(([jJ][pP][gG])|([tT][iI][fF]))
        b = [path for path in a]
        photo_files = [x for x in b if (re.search("(.tif$)|(.jpg$)|(.TIF$)|(.JPG$)",x) and (not re.search("_mask.",x)))]
        
        
        ## Add them
        if self.cfg["addPhotos"]["enabled"] and self.cfg["addPhotos"]["multispectral"]:
            self.doc.chunk.addPhotos(photo_files, layout = Metashape.MultiplaneLayout)
            self.logger.info('Photos (multispectral) added to project.')
        else:
            self.doc.chunk.addPhotos(photo_files)
            self.logger.info('Photos added to project.')
            
        # add masks if present (preferably in same 1XXMEDIA folder, with suffix {image_name}_mask.img_ext)
        # TODO: Try function below
        if "masks" in self.cfg and self.cfg["masks"]["enabled"]:
            self.logger.warning('Masks are currently a semi-unsupported feature, use with caution...')
            mask_count = 0
            for cam in self.doc.chunk.cameras:
                try:
                    self.doc.chunk.importMasks(
                        path = str(Path(self.cfg["masks"]["mask_path"],'{filename}_mask.JPG')),
                        cameras = [cam], 
                        source = self.cfg["masks"]["mask_source"]
                        )
                    self.logger.debug(f'Applied mask to camera {cam}')
                    mask_count += 1
                except:
                    pass
            self.logger.info(f'Masks have been applied to {mask_count} cameras.'+self._return_parameters(stage="masks"))
            
        ## Need to change the label on each camera so that it includes the containing folder
        for camera in self.doc.chunk.cameras:
            path = camera.photo.path
            path_parts = path.split("/")[-2:]
            newlabel = "/".join(path_parts)
            camera.label = newlabel
                       
        self.logger.info('Successfully relabeled cameras.')
            
        if self.cfg["addPhotos"]["enabled"] and self.cfg["addPhotos"]["remove_photo_location_metadata"]:
            for camera in self.doc.chunk.cameras:
                camera.reference.location = None
                camera.reference.rotation = None
                    
            self.logger.info('Removed camera reference coordinates for processing.')
            
    
        self.doc.save()
        self.logger.info('Finalised adding photos.'+self._return_parameters(stage="addPhotos"))
        
    def add_gcps(self):
        '''
        Add GCPs (GCP coordinates and the locations of GCPs in individual photos.
        See the helper script (and the comments therein) for details on how to prepare the data needed by this function: R/prep_gcps.R
        Alternatively, see the https://github.com/PeterBetlem/image_processing repo for automated Python processing based on aruco markers and OpenCV
        '''
        
        self.logger.info('Adding ground control points.')
        ## Tag specific pixels in specific images where GCPs are located
        path = Path(self.cfg["photo_path"], "gcps", "prepared", "gcp_imagecoords_table.csv")
        marker_pixel_data = pd.read_csv(path,names=["marker","camera","x","y"])
    
        for index, row in marker_pixel_data.iterrows():
            camera = _get_camera(self.doc.chunk, row.camera)
            if not camera:
                print(row.camera + " camera not found in project")
                continue
            
            marker = _get_marker(self.doc.chunk, str(int(row.marker)))
            if not marker:
                marker = self.doc.chunk.addMarker()
                marker.label = str(int(row.marker))
                
            marker.projections[camera] = Metashape.Marker.Projection((float(row.x), float(row.y)), True)
    
        ## Assign real-world coordinates to each GCP
        path = Path(self.cfg["photo_path"], "gcps", "prepared", "gcp_table.csv")
        marker_coordinate_data = pd.read_csv(path,names=["marker","x","y","z"])
        
        for index, row in marker_coordinate_data.iterrows():
            marker = _get_marker(self.doc.chunk, str(int(row.marker)))
            if not marker:
                marker = self.doc.chunk.addMarker()
                marker.label = str(int(row.marker))
                
            marker.reference.location = (float(row.x), float(row.y), float(row.z))
            marker.reference.accuracy = (
                self.cfg["addGCPs"]["marker_location_accuracy"], 
                self.cfg["addGCPs"]["marker_location_accuracy"], 
                self.cfg["addGCPs"]["marker_location_accuracy"]
                )
    
        self.doc.chunk.marker_location_accuracy = (
            self.cfg["addGCPs"]["marker_location_accuracy"], 
            self.cfg["addGCPs"]["marker_location_accuracy"], 
            self.cfg["addGCPs"]["marker_location_accuracy"]
            )
        self.doc.chunk.marker_projection_accuracy = self.cfg["addGCPs"]["marker_projection_accuracy"]
        self.doc.chunk.updateTransform()

        self.doc.save()
        self.logger.info('Ground control points added.'+self._return_parameters(stage="addGCPs"))
   
        return True
        
    def align_photos(self):
        """
        Create a network processing task for photo alignment, including the match
        photos, align cameras, and optimize camera steps.
        """
        
        self.logger.info('Aligning photos...')
        matchPhotos_dict = [
            "downscale",
            "filter_mask",
            "generic_preselection",
            "guided_matching",
            "keep_keypoints",
            "keypoint_limit",
            "mask_tiepoints",
            "reference_preselection",
            "reference_preselection_mode",
            "reset_matches",
            "subdivide_task",
            "tiepoint_limit",
            ]
        alignCameras_dict = [
            "adaptive_fitting",
            "min_image",
            "reset_alignment",
            "subdivide_task",
            ]
        
        match_parameters = {}
        for key, value in self.cfg["alignPhotos"].items():
            if key in matchPhotos_dict:
                match_parameters[key] = value 
        
        align_parameters = {}
        for key, value in self.cfg["alignPhotos"].items():
            if key in alignCameras_dict:
                align_parameters[key] = value 
            
        if self.network:            
            task = Metashape.Tasks.MatchPhotos()
            task.decode(match_parameters)
            self._encode_task(task)
            
            task = Metashape.Tasks.AlignCameras()
            task.decode(align_parameters)
            self._encode_task(task)
            
            if self.cfg["alignPhotos"]["enabled"] and self.cfg["alignPhotos"]["double_alignment"]:
                self.logger.warning("Re-alignment of non-aligned photos currently only supported in non-server mode...")
                
            self.logger.info('Photo-alignment tasks added to network batch list.'+self._return_parameters(stage="alignPhotos"))
                
        else:
            self.doc.chunk.matchPhotos(**match_parameters
                )
            self.logger.info('Photos matched.')
            self.doc.chunk.alignCameras(**align_parameters
                )
            self.doc.save()
            
            if self.cfg["alignPhotos"]["enabled"] and self.cfg["alignPhotos"]["double_alignment"]:
                align_parameters["reset_alignment"] = False
                aligned_photos = []   # empty list
                for camera in self.doc.chunk.cameras:
                    if camera.transform==None:
                        aligned_photos.append(camera)
               
                if len(aligned_photos)>0:
                    self.logger.info(f"Detected {len(aligned_photos)} cameras that failed alignment. Repeating alignment stage...")
                    self.doc.chunk.alignCameras(aligned_photos,**align_parameters)
                    self.doc.save()
                    aligned_photos = []   # empty list
                    for camera in self.doc.chunk.cameras:
                        if camera.transform==None:
                            aligned_photos.append(camera)
                    
                    self.logger.info(f"{len(aligned_photos)} non-aligned cameras remain.")
            self.logger.info('Cameras aligned.'+self._return_parameters(stage="alignPhotos"))
            
    def optimize_cameras(self):
        '''
        Optimize cameras
        '''   
        
        self.logger.info('Optimising camera alignment...')
        optimizeCameras_dict = [
            "adaptive_fitting",
            "fit_b1",
            "fit_b2",
            "fit_corrections",
            "adaptive_fitting",
            "fit_cx",
            "fit_cy",
            "fit_f",
            "fit_k1",
            "fit_k2",
            "fit_k3",
            "fit_k4",
            "fit_p1",
            "fit_p2",
            ]
        
        optimize_parameters = {}
        for key, value in self.cfg["optimizeCameras"].items():
            if key in optimizeCameras_dict:
                optimize_parameters[key] = value 
        
        # Disable camera locations as reference if specified in YML
        if self.cfg["addGCPs"]["enabled"] and self.cfg["addGCPs"]["optimize_w_gcps_only"]:
            self.logger.info('GCP-only optimisation enabled.')
            for camera in self.doc.chunk.cameras:
                camera.reference.enabled = False
        
        if self.network:
            
            task = Metashape.Tasks.OptimizeCameras()
            task.decode(optimize_parameters)
            self._encode_task(task)
            self.logger.info('Alignment-optimisation task added to network batch list.'+self._return_parameters(stage="optimizeCameras"))
            
        else:
            self.doc.chunk.optimizeCameras(
                **optimize_parameters
                )
            self.doc.save()
            self.logger.info('Optimised camera alignment.'+self._return_parameters(stage="optimizeCameras"))
            
    def build_dense_cloud(self):
        
        # TODO: consider splitting into separated depth map and dense cloud steps
        
        self.logger.info('Generating depth maps and dense cloud...')
        buildDepth_dict = [
            "downscale",
            "filter_mode",
            "reuse_depth",
            "max_neighbors",
            "subdivide_task",
            "workitem_size_cameras",
            "max_workgroup_size",
            ]
        
        depth_parameters = {}
        for key, value in self.cfg["buildDenseCloud"].items():
            if key in buildDepth_dict:
                depth_parameters[key] = value 
                
        buildDense_dict = [
            "point_colors",
            "point_confidence",
            "keep_depth",
            "max_neighbors",
            "subdivide_task",
            "workitem_size_cameras",
            "max_workgroup_size",
            ]
        
        dense_parameters = {}
        for key, value in self.cfg["buildDenseCloud"].items():
            if key in buildDense_dict:
                dense_parameters[key] = value 
        # Point confidence should always be calculated!
        dense_parameters["point_confidence"] = True    
        
        classify_dict = [
            "max_angle",
            "max_distance",
            "cell_size",
            ]
        
        classify_parameters = {}
        for key, value in self.cfg["buildDenseCloud"].items():
            if key in classify_dict:
                classify_parameters[key] = value
                
        if self.network:
            # build depth maps only instead of also building the dense cloud ##?? what does
            task = Metashape.Tasks.BuildDepthMaps()
            task.decode(depth_parameters)
            self._encode_task(task)
        
            # build dense cloud
            task = Metashape.Tasks.BuildDenseCloud()
            task.decode(dense_parameters)
            self._encode_task(task)
            self.logger.info('Depth map and dense cloud tasks added to network batch list.')
            
            # Classify ground points
            if self.cfg["buildDenseCloud"]["classify"]:
        
                task = Metashape.Tasks.ClassifyGroundPoints()
                task.decode(classify_parameters)
                self._encode_task(task)
                self.logger.info('Ground point classification task added to network batch list.')
            
        else:
            self.doc.chunk.buildDepthMaps(**depth_parameters)
            self.doc.save()
            self.logger.info('Depth maps built.')
            
            self.doc.chunk.buildDenseCloud(**dense_parameters)
            self.doc.save()
            self.logger.info('Dense cloud built.')
                       
            if self.cfg["buildDenseCloud"]["classify"]:
                self.doc.chunk.dense_cloud.classifyGroundPoints(**classify_parameters)
                self.doc.save()
                self.logger.info('Ground points classified.')
                
        self._return_parameters(stage="buildDenseCloud",log=True)
            
    def filter_dense_cloud(self):
        '''
        Filters the dense cloud. 
        Currently only supports local processing.
        Currently only supports point_confidence filtering

        '''
        if self.cfg["filterDenseCloud"]["point_confidence_max"]:
            if self.network:
                self.logger.warning("Point confidence for dense clouds currently not supported through the networking interface. Parameters ignored. Try running it locally.")
            else:
                self.logger.info("Removing dense points with 0<confidence<{self.cfg['filterDenseCloud']['point_confidence_max']}")
                self.doc.chunk.dense_cloud.setConfidenceFilter(0,self.cfg["filterDenseCloud"]["point_confidence_max"])
                self.doc.chunk.dense_cloud.removePoints(list(range(128))) #removes all "visible" points of the dense cloud
                self.doc.chunk.dense_cloud.resetFilters()
                
                self._return_parameters(stage="filterDenseCloud",log=True)
                self.doc.save()
        else:
            self.logger.warning("No filtering has occurred. Please configure 'filterDenseCloud'/'point_confidence_max' in the cfg file...")
            
    def build_mesh(self):
        '''
        Build mesh
        '''
        self.logger.info('Constructing a mesh...')
                
        buildMesh_dict = [
            "surface_type",
            "interpolation",
            "face_count",
            "face_count_custom",
            "source_data",
            "vertex_colors",
            "vertex_confidence",
            "metric_masks",
            "keep_depth",
            "trimming_radius",
            "workitem_size_cameras",
            "max_workgroup_size",
            ]
        
        mesh_parameters = {}
        for key, value in self.cfg["buildMesh"].items():
            if key in buildMesh_dict:
                mesh_parameters[key] = value 
                
        if self.network:
            
            # build depth maps only instead of also building the dense cloud ##?? what does
            task = Metashape.Tasks.BuildModel()
            task.decode(mesh_parameters)
            self._encode_task(task)
            self.logger.info('Mesh-building task added to network batch list.'+self._return_parameters(stage="buildMesh"))
                

        else:
            self.doc.chunk.buildModel(**mesh_parameters)
            self.doc.save()
            self.logger.info('Mesh has been constructed.'+self._return_parameters(stage="buildMesh"))
    
    def build_texture(self):
        '''
        Build UV maps and textures
        '''
        
        self.logger.info('Generating UV maps and textures...')
                
        buildUV_dict = [
            "mapping_mode",
            "page_count",
            "adaptive_resolution",
            ]
        
        uv_parameters = {}
        for key, value in self.cfg["buildTexture"].items():
            if key in buildUV_dict:
                uv_parameters[key] = value 
                
        buildTexture_dict = [
            "blending_mode",
            "texture_size",
            "fill_holes",
            "ghosting_filter",
            "texture_type",
            ]
        
        texture_parameters = {}
        for key, value in self.cfg["buildTexture"].items():
            if key in buildTexture_dict:
                texture_parameters[key] = value 
                
        if self.network:
            
            # build UV maps
            task = Metashape.Tasks.BuildUV()
            task.decode(uv_parameters)
            self._encode_task(task)
            self.logger.info('UV mapping task added to network batch list.')
                
     
            # build textures, requires UV maps.
            task = Metashape.Tasks.BuildTexture()
            task.decode(texture_parameters)
            self._encode_task(task)
            self.logger.info('Texture generation task added to network batch list.'+self._return_parameters(stage="buildTexture"))
            
        else:
            self.doc.chunk.buildUV(**uv_parameters)
            self.logger.info('UV map constructed.')
            
            self.doc.chunk.buildTexture(**texture_parameters)
            self.doc.save()
            self.logger.info('Textures constructed.'+self._return_parameters(stage="buildTexture"))

    def build_tiled_model(self):
        '''
        Build tiled model
        '''
        
        self.logger.info('Generating tiles for tiled model...')
             
        buildTiles_dict = [
            "pixel_size",
            "tile_size",
            "source_data",
            "face_count",
            "ghosting_filter",
            "transfer_texture",
            "keep_depth",
            "classes",
            "workitem_size_cameras",
            "max_workgroup_size"
            ]
        
        tile_parameters = {}
        for key, value in self.cfg["buildTiledModel"].items():
            if key in buildTiles_dict:
                tile_parameters[key] = value 
                
        if self.network:
            # build tiled model
            task = Metashape.Tasks.BuildTiledModel()
            task.decode(tile_parameters)
            self._encode_task(task)
            self.logger.info('Model tiling task added to network batch list.'+self._return_parameters(stage="buildTiledModel"))
            
        else:            
            self.doc.chunk.buildTiledModel(**tile_parameters)
            self.doc.save()
            self.logger.info('Tiled model constructed.'+self._return_parameters(stage="buildTiledModel"))

    def build_dem(self):
        '''
        Build dem
        '''
        
        self.logger.info('Generating DEM...')
             
        buildDEM_dict = [
            "source_data",
            "interpolation",
            "flip_x",
            "flip_y",
            "flip_z",
            "resolution",
            "workitem_size_tiles",
            "max_workgroup_size"
            ]
        
        dem_parameters = {}
        for key, value in self.cfg["buildDEM"].items():
            if key in buildDEM_dict:
                dem_parameters[key] = value 
                
        if self.network:
            # build dem
            task = Metashape.Tasks.BuildDem()
            task.decode(dem_parameters)
            self._encode_task(task)
            self.logger.info('DEM generation task added to network batch list.'+self._return_parameters(stage="buildDEM"))

            
        else:            
            self.doc.chunk.buildDem(**dem_parameters)
            self.doc.save()
            self.logger.info('DEM constructed.'+self._return_parameters(stage="buildDEM"))

        
    def export_report(self):
        """
        Function to automatically create reports
        """
        output_file = str(Path(
            self.cfg["output_path"], 
            self.run_id+'_report.pdf'
            ))
        if self.network:
            task = Metashape.Tasks.ExportReport()
            task.path = output_file
            self._encode_task(task)
            self.logger.info(f'A processing report will be exported to {output_file}.')
            
        else:
            self.doc.chunk.exportReport(path = output_file)
            self.doc.save()
            self.logger.info(f'A processing report has been exported to {output_file}.')
    
    def _network_submit_batch(self):
        """
        Script that submits the generated task list to the network.
        """
        self.doc.save()
        
        batch_id = self.client.createBatch(str(self.project_file), self.task_batch)
        self.client.resumeBatch(batch_id)
        self.client.disconnect()
        
        self.logger.info("Project file has been submitted to the pc cluster for processing...")
                    
        #self.doc = Metashape.Document() # needed to remove the lock on the project.    
        
        
if __name__ == "__main__":
    manual_config_file = "../config/close-range_photogrammetry.yml"
    try:
        config_file = sys.argv[1]
    except:
        config_file = manual_config_file
        
    logger = logging.getLogger(__name__)
    try:
        MetashapeProcessing(config_file,logger=logger)
    except:
        _msteams_connector(task = "abort")
        logger.exception('')
        
