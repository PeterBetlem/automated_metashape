# -*- coding: utf-8 -*-
"""
Created on Sat Aug 29 17:21:08 2020

@author: Peter Betlem
@institution: The University Centre in Svalbard
@year: 2020
"""

import Metashape

from pathlib import Path
import os
import sys

metaproj = Path(r'C:\Users\Peter\OneDrive\Bilder\test\metashape\test_name_run001_20200829T1750.psx')
doc = Metashape.Document()
doc.open(metaproj.as_posix())

doc.chunk.cameras[0].photo.meta["Exif/FocalLength"]
doc.chunk.model.meta