# Copyright (C) 2001-2007 Python Software Foundation
# Author: Barry Warsaw
# Contact: email-sig@python.org

try:
    import Metashape
except ModuleNotFoundError as e:
    print(e)
    print("Unable to import Metashape functions." + \
          "Please see readme for instructions." + \
          "This limits scrips capabilities to marker-functions only...")

import pkg_resources
import distutils.dist
import io

am = pkg_resources.get_distribution('automated_metashape')
metadata_str = am.get_metadata(am.PKG_INFO)
metadata_obj = distutils.dist.DistributionMetadata()
metadata_obj.read_pkg_file(io.StringIO(metadata_str))

__version__ = metadata_obj.version
__author__ = metadata_obj.author
__author_email__ = metadata_obj.author_email
__repository__ = metadata_obj.url
__license__ = metadata_obj.license

