# =================================================================
#
# Author: Etienne Pelletier <etienne.pelletier@canada.ca>
#
# Copyright (c) 2020 Etienne Pelletier
# Copyright (c) 2022 Tom Kralidis
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# =================================================================

from datetime import datetime
from itertools import groupby
import logging
import os
from pathlib import Path

import click
from elasticsearch.exceptions import ConflictError
from parse import parse
from osgeo import ogr

from msc_pygeoapi import cli_options
from msc_pygeoapi.connector.elasticsearch_ import ElasticsearchConnector
from msc_pygeoapi.loader.base import BaseLoader
from msc_pygeoapi.util import (
    configure_es_connection,
    strftime_rfc3339
)

LOGGER = logging.getLogger(__name__)

# index settings
INDEX_NAME = 'hurricanes_realtime_{}'

FILE_PROPERTIES = {
    'pts': {
        'STORMNAME': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'STORMTYPE': {
            'type': 'byte'
        },
        'BASIN': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'ADVDATE': {
            'type': 'date',
            'format': 'date_time_no_millis',
            'ignore_malformed': False,
        },
        'STORMFORCE': {
            'type': 'byte'
        },
        'LAT': {
            'type': 'float'
        },
        'LON': {
            'type': 'float'
        },
        'TIMESTAMP': {
            'type': 'date',
            'format': 'date_time_no_millis',
            'ignore_malformed': False,
        },
        'VALIDTIME': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'TAU': {
            'type': 'short'
        },
        'MAXWIND': {
            'type': 'short'
        },
        'MSLP': {
            'type': 'float'
        },
        'TCDVLP': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'DATELBL': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'TIMEZONE': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'ERRCT': {
            'type': 'float'
        },
        'R34NE': {
            'type': 'short'
        },
        'R34SE': {
            'type': 'short'
        },
        'R34SW': {
            'type': 'short'
        },
        'R34NW': {
            'type': 'short'
        },
        'R48NE': {
            'type': 'short'
        },
        'R48SE': {
            'type': 'short'
        },
        'R48SW': {
            'type': 'short'
        },
        'R48NW': {
            'type': 'short'
        },
        'R64NE': {
            'type': 'short'
        },
        'R64SE': {
            'type': 'short'
        },
        'R64SW': {
            'type': 'short'
        },
        'R64NW': {
            'type': 'short'
        },
        'active': {
            'type': 'boolean'
        },
        'filename': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'filedate': {
            'type': 'date',
            'format': 'date_time_no_millis',
            'ignore_malformed': False,
        }
    },
    'rad': {
        'STORMNAME': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'WINDFORCE': {
            'type': 'float'
        },
        'TIMESTAMP': {
            'type': 'date',
            'format': 'date_time_no_millis',
            'ignore_malformed': False,
        },
        'VALIDTIME': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'active': {
            'type': 'boolean'
        },
        'filename': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'filedate': {
            'type': 'date',
            'format': 'date_time_no_millis',
            'ignore_malformed': False,
        }
    },
    'err': {
        'STORMNAME': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'active': {
            'type': 'boolean'
        },
        'filename': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'filedate': {
            'type': 'date',
            'format': 'date_time_no_millis',
            'ignore_malformed': False,
        }
    },
    'lin': {
        'STORMNAME': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'STORMTYPE': {
            'type': 'byte'
        },
        'BASIN': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'active': {
            'type': 'boolean'
        },
        'filename': {
            'type': 'text',
            'fields': {
                'raw': {'type': 'keyword'}
            }
        },
        'filedate': {
            'type': 'date',
            'format': 'date_time_no_millis',
            'ignore_malformed': False,
        }
    }
}

SETTINGS = {
    'settings': {
        'number_of_shards': 1,
        'number_of_replicas': 0
    },
    'mappings': {
        'properties': {
            'geometry': {
                'type': 'geo_shape'
            },
            'properties': {
                'properties': None
            }
        }
    }
}

INDICES = [INDEX_NAME.format(weather_var) for weather_var in FILE_PROPERTIES]


class HurricanesRealtimeLoader(BaseLoader):
    """Hurricanes Real-time loader"""

    def __init__(self, conn_config={}):
        """initializer"""

        BaseLoader.__init__(self)

        self.conn = ElasticsearchConnector(conn_config)
        self.filepath = None
        self.date_ = None
        self.fh = None
        self.storm_name = None
        self.storm_variable = None
        self.items = []

        # create storm variable indices if it don't exist
        for item in FILE_PROPERTIES:
            SETTINGS['mappings']['properties']['properties'][
                'properties'
            ] = FILE_PROPERTIES[item]
            self.conn.create(INDEX_NAME.format(item), SETTINGS)

    def parse_filename(self):
        """
        Parses a hurricane filename in order to get the date, forecast issued
        time, storm name, and  storm variable.
        :return: `bool` of parse status
        """
        # parse filepath
        pattern = '{date_}_{fh}_{storm_name}.{storm_variable}.' \
                  '{file_extension}'
        filename = self.filepath.name
        parsed_filename = parse(pattern, filename)

        # set class variables
        self.date_ = datetime.strptime(parsed_filename.named['date_'],
                                       '%Y%m%d')
        self.fh = parsed_filename.named['fh']
        self.storm_name = parsed_filename.named['storm_name']
        self.storm_variable = parsed_filename.named['storm_variable']

        return True

    def check_shapefile_deps(self):
        """
        Check that all shapefile dependencies are available
        :return: `bool` of check result
        """
        dependencies = ['.shp', '.shx', '.dbf', '.prj']
        return all([self.filepath.with_suffix(suffix).exists() for
                    suffix in dependencies])

    # TODO: Remove once upstream data is patched
    @staticmethod
    def clean_consecutive_coordinates(coordinates):
        """
        Temporary fix for issues with upstream data.
        Removes consecutive coordinate points from GeoJSON coordinates
        :param coordinates: list of GeoJSON coordinates
        :return:
        """
        return [[k for k, g in groupby(coordinate)] for
                coordinate in coordinates]

    def deactivate_old_forecasts(self):
        """
        Deactivates previously added forecasts for a specific storm name.
        :return: `bool` of deactivation status
        """
        query = {
            "script": "ctx._source.properties.active=false",
            "query": {
                "bool": {
                    "must": [
                        {"match": {"properties.STORMNAME": self.storm_name}},
                        {"match": {"properties.active": True}},
                    ]
                }
            }
        }

        try:
            self.conn.Elasticsearch.update_by_query(index=INDEX_NAME.format(
                self.storm_variable), body=query)
        except ConflictError:
            LOGGER.warning("Conflict error detected. Refreshing index and "
                           "retrying update by query.")
            self.conn.Elasticsearch.indices.refresh(index=INDEX_NAME.format(
                self.storm_variable))
            self.conn.Elasticsearch.update_by_query(index=INDEX_NAME.format(
                self.storm_variable), body=query)

        return True

    def generate_geojson_features(self):
        """
        Generates and yields a series of storm forecasts,
        one for each feature in <self.filepath>. Observations are returned as
        Elasticsearch bulk API upsert actions, with documents in GeoJSON to
        match the Elasticsearch index mappings.
        :returns: Generator of Elasticsearch actions to upsert the storm
                  forecasts
        """
        driver = ogr.GetDriverByName('ESRI Shapefile')
        filepath = str(self.filepath.resolve())
        data = driver.Open(filepath, 0)
        lyr = data.GetLayer(0)
        file_datetime_str = strftime_rfc3339(self.date_)

        for feature in lyr:
            feature_json = feature.ExportToJson(as_object=True)
            feature_json['properties']['active'] = True
            feature_json['properties'][
                'filename'] = self.filepath.stem
            feature_json['properties'][
                'filedate'] = file_datetime_str  # noqa

            # TODO: Remove once upstream data is patched
            # clean rad consecutive coordinates in geometry (temporary fix)
            if self.storm_variable == 'rad':
                feature_json['geometry'][
                    'coordinates'] = self.clean_consecutive_coordinates(
                    feature_json['geometry']['coordinates'])

            # format pts ADVDATE
            if self.storm_variable == 'pts':
                feature_json['properties']['ADVDATE'] = \
                    strftime_rfc3339(
                        datetime.strptime(
                            feature_json['properties']['ADVDATE'],
                            '%y%m%d/%H%M'
                        )
                    )

            self.items.append(feature_json)

            action = {
                '_id': '{}-{}-{}-{}-{}'.format(self.storm_name,
                                               self.storm_variable,
                                               file_datetime_str,
                                               self.fh,
                                               feature_json['id']),
                '_index': INDEX_NAME.format(self.storm_variable),
                '_op_type': 'update',
                'doc': feature_json,
                'doc_as_upsert': True
            }

            yield action

    def load_data(self, filepath):
        """
        loads data from event to target
        :returns: `bool` of status result
        """

        self.filepath = Path(filepath)

        # set class variables from filename
        self.parse_filename()

        LOGGER.debug('Received file {}'.format(self.filepath))

        # check for shapefile dependencies
        if self.check_shapefile_deps():

            # deactivate old forecasts for current storm name
            self.deactivate_old_forecasts()

            # generate geojson features
            package = self.generate_geojson_features()
            self.conn.submit_elastic_package(package, request_size=80000)

            return True

        else:
            LOGGER.debug("All Shapefile dependencies not found. Ignoring "
                         "file...")
            return False


@click.group()
def hurricanes():
    """Manages hurricanes indices"""
    pass


@click.command()
@click.pass_context
@cli_options.OPTION_FILE()
@cli_options.OPTION_DIRECTORY()
@cli_options.OPTION_ELASTICSEARCH()
@cli_options.OPTION_ES_USERNAME()
@cli_options.OPTION_ES_PASSWORD()
@cli_options.OPTION_ES_IGNORE_CERTS()
def add(ctx, file_, directory, es, username, password, ignore_certs):
    """Add hurricane data to Elasticsearch"""

    if all([file_ is None, directory is None]):
        raise click.ClickException('Missing --file/-f or --dir/-d option')

    conn_config = configure_es_connection(es, username, password, ignore_certs)

    files_to_process = []

    if file_ is not None:
        files_to_process = [file_]
    elif directory is not None:
        for root, dirs, files in os.walk(directory):
            for f in [file for file in files if file.endswith('.shp')]:
                files_to_process.append(os.path.join(root, f))
        files_to_process.sort(key=os.path.getmtime)

    for file_to_process in files_to_process:
        loader = HurricanesRealtimeLoader(conn_config)
        result = loader.load_data(file_to_process)
        if not result:
            click.echo('features not generated')


@click.command()
@click.pass_context
@cli_options.OPTION_DAYS(
    required=True,
    help='Delete documents older than n days'
)
@cli_options.OPTION_ELASTICSEARCH()
@cli_options.OPTION_ES_USERNAME()
@cli_options.OPTION_ES_PASSWORD()
@cli_options.OPTION_ES_IGNORE_CERTS()
def deactivate(ctx, days, es, username, password, ignore_certs):
    """deactivate hurricane forecasts older than N days"""

    conn_config = configure_es_connection(es, username, password, ignore_certs)
    conn = ElasticsearchConnector(conn_config)

    for index in INDICES:
        query = {
            "script": "ctx._source.properties.active=false",
            "query": {
                "range": {
                    "properties.filedate": {
                        "lte": "now-{}d".format(days)
                    }
                }
            }
        }

        conn.Elasticsearch.update_by_query(index=index, body=query)

    return True


@click.command()
@click.pass_context
@click.option('--index_name', '-i',
              type=click.Choice(INDICES),
              help='msc-geousage elasticsearch index name to delete')
@cli_options.OPTION_ELASTICSEARCH()
@cli_options.OPTION_ES_USERNAME()
@cli_options.OPTION_ES_PASSWORD()
@cli_options.OPTION_ES_IGNORE_CERTS()
def delete_indexes(ctx, index_name, es, username, password, ignore_certs):
    """
    Delete a particular ES index with a given name as argument or all if no
    argument is passed
    """
    conn_config = configure_es_connection(es, username, password, ignore_certs)
    conn = ElasticsearchConnector(conn_config)

    if index_name:
        if click.confirm(
                'Are you sure you want to delete ES index named: {}?'.format(
                    click.style(index_name, fg='red')), abort=True):
            LOGGER.info('Deleting ES index {}'.format(index_name))
            conn.delete(index_name)
            return True
    else:
        if click.confirm(
                'Are you sure you want to delete {} hurricane'
                ' indices ({})?'.format(click.style('ALL', fg='red'),
                                        click.style(", ".join(INDICES),
                                                    fg='red')),
                abort=True):
            conn.delete(",".join(INDICES))
            return True


hurricanes.add_command(add)
hurricanes.add_command(deactivate)
hurricanes.add_command(delete_indexes)
