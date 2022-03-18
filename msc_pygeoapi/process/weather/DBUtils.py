from __future__ import annotations
import sqlite3
import collections
from itertools import islice
from dataclasses import dataclass
from typing import Iterable, Union, List, Tuple, ClassVar, Dict, ByteString, Sequence
from datetime import datetime
import pytz
from pyrfc3339.utils import FixedOffset

import logging
from builtins import isinstance

logger = logging.getLogger(__name__)


#===============================================================================
# UTILITARY FUNCTIONS
#===============================================================================
def consume(iterator: Iterable, n: int=None) -> None:
    """"Advance the iterator n-steps ahead. If n is none, consume
        entirely."""
    if n is None:
        # feed the entire iterator into a zero-length deque
        collections.deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(islice(iterator, n, n), None)


def parse(timestamp: str,
          utc: bool=False,
          produce_naive: bool=False):
    """
    See pyrfc3339.parse for actual doc.
    
    Modified pyrfc3339.parse to allow for 7 decimals seconds 
    which are the default in Aquarius TimeSeries 
    and do not respect the iso8601 standard.
    
    Necessary if trying to work from Aquarius points directly.
    """

    parse_re = re.compile(r'''^(?:(?:(?P<date_fullyear>[0-9]{4})\-(?P<date_month>[0-9]{2})\-(?P<date_mday>[0-9]{2}))T(?:(?:(?P<time_hour>[0-9]{2})\:(?P<time_minute>[0-9]{2})\:(?P<time_second>[0-9]{2})(?P<time_secfrac>(?:\.[0-9]{1,}))?)(?P<time_offset>(?:Z|(?P<time_numoffset>(?P<time_houroffset>(?:\+|\-)[0-9]{2})\:(?P<time_minuteoffset>[0-9]{2}))))))$''',
                          re.I | re.X)

    match = parse_re.match(timestamp)

    if match is not None:
        if match.group('time_offset') in ["Z", "z", "+00:00", "-00:00"]:
            if produce_naive is True:
                tzinfo = None
            else:
                tzinfo = pytz.utc
        else:
            if produce_naive is True:
                raise ValueError("cannot produce a naive datetime from " + 
                                 "a local timestamp")
            else:
                tzinfo = FixedOffset(int(match.group('time_houroffset')),
                                     int(match.group('time_minuteoffset')))

        secfrac = match.group('time_secfrac')

        if secfrac is None:
            microsecond = 0
        elif float(secfrac) == 10 ** -(len(secfrac) - 1):
            microsecond = 1
        else:
            diff = (len(secfrac) - 1) - 6
            diff = 0 if diff < 0 else diff
            ms = f'{secfrac:<07}'
            microsecond = float(secfrac[:-diff]) if diff else float(secfrac)
            microsecond = int(microsecond * 10 ** 6)
            if ms[-1] == '1' and ms[-2] == '0':
                microsecond += 1

        dt_out = datetime(year=int(match.group('date_fullyear')),
                          month=int(match.group('date_month')),
                          day=int(match.group('date_mday')),
                          hour=int(match.group('time_hour')),
                          minute=int(match.group('time_minute')),
                          second=int(match.group('time_second')),
                          microsecond=microsecond,
                          tzinfo=tzinfo)

        if utc:
            dt_out = dt_out.astimezone(pytz.utc)
        return dt_out
    else:
        raise ValueError("timestamp does not conform to RFC 3339")

    
def datetime_from_iso8601_string(text: Union[str, datetime]) -> datetime:
        """Parses the ISO8601 timestamp to a standard python datetime object"""
        try:
            return pyrfc3339.parse(text)
        except TypeError as exc:  # @UnusedVariable
            if type(text) == dt.datetime:
                return text
            # logger.exception(exc)

            
def convert_timestamp(val: ByteString) -> datetime:
    """
    Timezone aware datetime converter
    
    Uses the usual converter from DBapi2 
    in case of ValueError , uses the timezone-aware one from Utils
    """
    try:
        datepart, timepart = val.split(b" ")
        year, month, day = map(int, datepart.split(b"-"))
        timepart_full = timepart.split(b".")
        hours, minutes, seconds = map(int, timepart_full[0].split(b":"))
        if len(timepart_full) == 2:
            microseconds = int('{:0<6.6}'.format(timepart_full[1].decode()))
        else:
            microseconds = 0
    
        val = datetime.datetime(year, month, day, hours, minutes, seconds, microseconds)
        return val
    except ValueError:
        # The standard convert function doesn't accept timezones
        # Adding functionality while still keeping the original naive datetime converter case
        # => '2019-01-01 00:00:00-05:00'
        # => '9999-12-31T23:59:59.9999999+00:00'
        return datetime_from_iso8601_string(val.decode().replace(' ', 'T'))

    
# Mapping the timestamp datatype to the modified converter.
sqlite3.register_converter("timestamp", convert_timestamp)


#===============================================================================
# Composition/Mixin
#===============================================================================
@dataclass
class BaseObjectWithPostInit(object):

    def __post_init__(self):
        # just intercept the __post_init__ calls so they
        # aren't relayed to `object`
        pass


@dataclass 
class SQLiteConnect(BaseObjectWithPostInit):
    db_file_path: str = None
    
    def __post_init__(self) -> None:
        super().__post_init__()
    
    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file_path,
                               detect_types=sqlite3.PARSE_DECLTYPES)


@dataclass 
class SQLiteStationTable: 

    def __post_init__(self):
        super().__post_init__()
    
    def create_station_table(self) -> None:
        with self.connect() as con:
            sql = f"""
                  CREATE TABLE IF NOT EXISTS Station(
                  id INTEGER PRIMARY KEY,
                  identifier TEXT,
                  name TEXT,
                  latitude REAL,
                  longitude REAL,
                  geometry {self.geometry_type}
                  )
                  """
            con.execute(sql)
            
    def get_station_id_from_identifier(self,
                                       identifier: str
                                       ) -> int:
        with self.connect() as con:
            sql = """
                  SELECT 
                      id 
                  FROM 
                      Station
                  WHERE
                      identifier = ?
                  """
            return next(con.execute(sql,
                                    (identifier,)
                                   ),
                        None)
    
    def get_station_id_from_identifiers_and_ids(self,
                                                identifiers: Sequence[str],
                                                ids: Sequence[int]) -> list[int]:
        if station_identifier:
                if isinstance(station_identifier, str):
                    id = [self.get_station_id_from_identifier(station_identifier)]
                elif isinstance(station_identifier, collections.abc.Sequence):
                    id = [self.get_station_id_from_identifier(stn)
                          for stn in station_identifier 
                          if self.get_station_id_from_identifier(stn)]
        if station_id:
            if isinstance(station_identifier, collections.abc.Sequence) and id:
                station_id.extend(id)
            else:
                station_id = [station_id]
        return station_id
    
    def get_station_id_in_clause_from_identifiers_and_ids(self,
                                                      identifiers: Sequence[str],
                                                      ids: Sequence[int]) -> str:
        return ','.join(f"'{stn}'" 
                              for 
                                stn 
                              in 
                                self.get_station_id_from_identifiers_and_ids(identifiers,
                                                                             ids)
                             )

    
@dataclass  
class SQLiteTriggerSwitch:
    
    def __post_init__(self):
        super().__post_init__()
        
    def create_trigger_status_table(self) -> None:
        with self.connect() as con:
            sql = """
                  CREATE TABLE IF NOT EXISTS TriggerStatus(
                  triggers_are_on BOOLEAN NOT NULL DEFAULT 0 CHECK(triggers_are_on IN (0,1))
                  )
                  """
            con.execute(sql)
            
    def toggle_trigger_status(self) -> None:
        with self.connect() as con:
            sql = """
                  UPDATE TriggerStatus SET triggers_are_on=ABS(triggers_are_on-1)
                  """
            con.execute(sql)
            
    def turn_triggers_off(self) -> None:
        with self.connect() as con:
            sql = """
                  UPDATE TriggerStatus SET triggers_are_on=0
                  """
            con.execute(sql)
            
    def turn_triggers_on(self) -> None:
        with self.connect() as con:
            sql = """
                  UPDATE TriggerStatus SET triggers_are_on=1
                  """
            con.execute(sql) 

            
@dataclass
class SQLiteWithStationAndTrigger(SQLiteStationTable, SQLiteTriggerSwitch, SQLiteConnect):

    def __post_init__(self) -> None:
        super().__post_init__()


@dataclass
class SQLiteJSONGeometryType:
    """
    Method for management of geometry
    
    From a TEXT data column
    
    Assuming GeoJSON text
    """
    geometry_type: str = None
    forecast_station_name: str = None
    forecast_basin_name: str = None
    
    def __post_init__(self):
        self.geometry_type = 'TEXT'
        super().__post_init__()
        
    def get_station_location_geojson_from_station_id(self,
                                     station_id: int
                                     ) -> str:
        with self.connect() as con:
            sql = f"""SELECT 
                        geometry 
                     FROM
                        {self.forecast_station_name}
                     WHERE
                        station_id = ?
                   """
            return next(con.execute(sql, (station_id,)), None)
    
    def get_station_basin_geojson_from_station_id(self,
                                                  station_id: int
                                                  ) -> str:
        with self.connect() as con:
            sql = f"""SELECT 
                        geometry 
                     FROM
                        {self.forecast_basin_name}
                     WHERE
                        station_id = ?
                   """
            return next(con.execute(sql, (station_id,)), None)
        
    def get_geom_insert_sql(self,
                            geom: str) -> str:
        """
        Assuming the insert is already GeoJSON
        """
        return geom

    
@dataclass
class SpatialiteGeometryType:
    """
    Method for management of geometry
    
    From a Spatialite Geometry column
    see: http://www.gaia-gis.it/gaia-sins/spatialite-sql-5.0.1.html
    """
    geometry_type: str = None
    forecast_station_name: str = None
    forecast_basin_name: str = None
    
    def __post_init__(self) -> None:
        self.geometry_type = 'Geometry'
        super().__post_init__()
    
    def get_station_location_geojson_from_station_id(self,
                                    station_id: int) -> str:
        with self.connect() as con:
            # second term in precision, 4 digits here, default is 15
            sql = f"""SELECT 
                        AsGeoJSON(geometry,4)
                     FROM
                        {self.forecast_station_name}
                     WHERE
                        station_id = ?
                   """
            return next(con.execute(sql, (station_id,)), None)
        
    def get_station_basin_geojson_from_station_id(self,
                                                  station_id: int) -> str:
        with self.connect() as con:
            # second term in precision, 4 digits here, default is 15
            sql = f"""SELECT 
                        AsGeoJSON(geometry,4)
                     FROM
                        {self.forecast_basin_name}
                     WHERE
                        station_id = ?
                   """
            return next(con.execute(sql, (station_id,)), None)
    

@dataclass
class AquariusDataDBUtil(SQLiteWithStationAndTrigger):
    """
    Assuming sqlite here
    
    Possibility of using postgres was discussed
    
    Using ANSI SQL here so only inheriting the class and simply 
    changing the connect method is necessary
    
    Possible that the upsert may need modifications but as of 2022-02-15 
    SQLite uses the same upsert syntax from PostgreSQL.
    
    PostgreSQL can disable triggers more easily too
    """
    # Approved and "not approved views"
    # Add other approval levels and where clauses if need be
    where_clauses: ClassVar[Dict[str, str]] = None
    # Tables of the type int->description
    point_meta_int_tables: ClassVar[Tuple[str]] = None
    # Tables of the type str->description
    point_meta_str_tables: ClassVar[Tuple[str]] = None
    
    def __post_init__(self) -> None:
        super().__post_init__()
        AquariusDataDBUtil.where_clauses = {'approved': '>= 1100',
                              'preliminary': '< 1100'}
        AquariusDataDBUtil.point_meta_int_tables = ('Approval',)
        AquariusDataDBUtil.point_meta_str_tables = ('Qualifier', 'Grade',)
    
    def get_table_name(self,
                       aggregate_name: str='daily') -> None:
        tb_name: str = (f"TS{aggregate_name}Aggregate"
                    if 
                    aggregate_name.lower() in ('daily', 'monthly', 'yearly', 'hourly')
                    else 
                        'AquariusTimeSeriesData'
                        if 
                            aggregate_name.lower() == 'aq_data'
                        else 
                            None
                  )
        if tb_name is None:
            logger.error('No valid table name provided, exiting')
        return tb_name
    
    def get_geom_insert_sql(self,
                            geom: str) -> str:
        """
        Assuming the insert is already GeoJSON
        """
        return f"GeomFromGeoJSON({geom})"
    
    #===========================================================================
    # TRIGGERS
    #===========================================================================
    
    def create_triggers_for_aggregate(self,
                                      aggregate_name: str='daily'
                                      ) -> None:
        self.create_trigger_status_table()
        # Update log
        self.create_update_log_table(aggregate_name)
        self.create_update_triggers(aggregate_name)
        # Insert log
        self.create_delete_or_insert_changes_log_table(aggregate_name,
                                                       action='insert')
        self.create_delete_or_insert_trigger(aggregate_name,
                                             action='insert')
        # Delete log
        self.create_delete_or_insert_changes_log_table(aggregate_name,
                                                       action='delete')
        self.create_delete_or_insert_trigger(aggregate_name,
                                             action='delete')
        
    def create_delete_or_insert_changes_log_table(self,
                                                  aggregate_name: str='daily',
                                                  action='INSERT') -> None:
        table_name: str = self.get_table_name(aggregate_name=aggregate_name)
        reference_row = 'new' if action.lower() == 'insert' else 'old'
        with self.connect() as con:
            sql = f"""
              CREATE TABLE IF NOT EXISTS {table_name}_{action.upper()}_log(
                  timeseries_uniqueid TEXT,
                  value_timestamp TIMESTAMP,
                  changes_timestamp TIMESTAMP,
                  value_{reference_row} REAL,
                  approval_{reference_row} INT,
                  grade_{reference_row} TEXT,
                  qualifiers_{reference_row} TEXT,
                  PRIMARY KEY(timeseries_uniqueid,value_timestamp,changes_timestamp) ON CONFLICT IGNORE
              )
              """
            con.execute(sql)
            
    def create_delete_or_insert_trigger(self,
                                        aggregate_name: str='daily',
                                        action='INSERT') -> None:
        reference_row = 'new' if action.lower() == 'insert' else 'old'
        table_name: str = self.get_table_name(aggregate_name=aggregate_name)
        sql = f"""
              CREATE TRIGGER IF NOT EXISTS log_{table_name}_{action.upper()}
              AFTER {action.upper()}
              ON {table_name}
              WHEN (SELECT triggers_are_on FROM TriggerStatus)=1
              BEGIN
              INSERT INTO
                  {table_name}_{action.upper()}_log(timeseries_uniqueid,
                                           value_timestamp,
                                           changes_timestamp,
                                           value_{reference_row},
                                           approval_{reference_row},
                                           grade_{reference_row},
                                           qualifiers_{reference_row}
                                           )
              VALUES({reference_row}.timeseries_uniqueid,
                     {reference_row}.value_timestamp,
                     CURRENT_TIMESTAMP,
                     {reference_row}.value,
                     {reference_row}.approval,
                     {reference_row}.grade,
                     {reference_row}.qualifiers
                     );
              END;
              """
        with self.connect() as con:
            con.execute(sql)
            
    def create_update_log_table(self,
                                aggregate_name: str='daily'
                                ) -> None:
        
        table_name: str = self.get_table_name(aggregate_name=aggregate_name) 
        # TODO : Maybe add an index on the ts_id?
        with self.connect() as con:
            sql = f"""
              CREATE TABLE IF NOT EXISTS {table_name}_UPDATE_log(
              timeseries_uniqueid TEXT,
              value_timestamp TIMESTAMP,
              changes_timestamp TIMESTAMP,
              value_old REAL,
              value_new REAL,
              approval_old INT,
              approval_new INT,
              grade_old TEXT,
              grade_new TEXT,
              qualifiers_old TEXT,
              qualifiers_new TEXT,
              PRIMARY KEY(timeseries_uniqueid,value_timestamp,changes_timestamp) ON CONFLICT IGNORE
              )
              """
            con.execute(sql)
    
    def create_update_triggers(self,
                                aggregate_name: str='daily'
                                ) -> None:
        table_name: str = self.get_table_name(aggregate_name=aggregate_name)
        sql = f"""
              CREATE TRIGGER IF NOT EXISTS log_{table_name}_UPDATE
              AFTER UPDATE
              ON {table_name}_UPDATE_log
              WHEN (SELECT triggers_are_on FROM TriggerStatus)=1
              BEGIN
              INSERT INTO
                  {table_name}_UPDATE_log(timeseries_uniqueid,
                                           value_timestamp,
                                           changes_timestamp,
                                           value_old,
                                           value_new,
                                           approval_old,
                                           approval_new,
                                           grade_old,
                                           grade_new,
                                           qualifiers_old,
                                           qualifiers_new
                                           )
              VALUES(new.timeseries_uniqueid,
                     new.value_timestamp,
                     CURRENT_TIMESTAMP,
                     old.value,
                     new.value,
                     old.approval,
                     new.approval,
                     old.grade,
                     new.grade,
                     old.qualifiers,
                     new.qualifiers
                     );
              END;
              """
        with self.connect() as con:
            con.execute(sql)

    #===========================================================================
    # AGGREGATES AND REALTIME TABLES CREATIONS
    #===========================================================================
    def create_aggregate_table(self,
                               aggregate_name: str='daily') -> None:
        table_name: str = self.get_table_name(aggregate_name=aggregate_name)
        with self.connect() as con:
            sql: str = f"""CREATE TABLE IF NOT EXISTS {table_name}(
                             timeseries_uniqueid TEXT NOT NULL,
                             station_id INTEGER REFERENCES Station(id),
                             parameter TEXT,
                             value_timestamp TIMESTAMP,
                             value REAL,
                             approval INT REFERENCES Approval(id),
                             grade TEXT REFERENCES Grade(id),
                             qualifiers TEXT,
                             qualifierCodes TEXT,
                             PRIMARY KEY(timeseries_uniqueid,value_timestamp) ON CONFLICT REPLACE
                             )
                         """
            con.execute(sql)
            
    def create_aggregate_view(self,
                              aggregate_name: str='daily',
                              approval_level: str='Approved') -> None:
        
        table_name: str = self.get_table_name(aggregate_name=aggregate_name)
        where_clause = self.where_clauses.get(approval_level.lower(), None)
        if not where_clause:
            raise AttributeError(f"PredictionsUtilDB has no view defined for {approval_level}")
        with self.connect() as con:
            sql = f"""
                    CREATE VIEW IF NOT EXISTS 
                        {table_name}{approval_level}
                    AS 
                        SELECT * FROM {table_name} WHERE approval >= 1100     
                 """
            con.execute(sql)
    
    def create_aggregate_tables(self) -> None:
        """
        Creation of the tables and triggers
        
        Availability is from yearly to realtime
        """
        consume(self.create_aggregate_table(aggregate_name)
                for aggregate_name
                    in ('daily', 'monthly', 'yearly', 'hourly', 'aq_data')
               )
        
    def create_all_triggers(self) -> None:
        consume(self.create_triggers_for_aggregate(aggregate_name)
                for aggregate_name
                    in ('daily', 'monthly', 'yearly', 'hourly', 'aq_data')
               )
    
    def create_point_meta_table(self,
                                meta_name: str) -> None:
        if meta_name.capitalize() in self.point_meta_int_tables:
            key_type = 'INT'
        elif meta_name.capitalize() in self.point_meta_str_tables:
            key_type = 'TEXT'
        else:
            key_type = None
        if key_type is None:
            raise AttributeError(f"PredictionsUtilDB does not have a point metadata table named {meta_name}")
        table_name = meta_name.capitalize()
        with self.connect() as con:
            sql = f"""
                    CREATE TABLE IF NOT EXISTS {table_name}(
                    id {key_type} PRIMARY KEY NOT NULL,
                    name TEXT
                    )
                 """
            con.execute(sql)
    
    def create_point_meta_tables(self) -> None:
        for meta in self.point_meta_int_tables:
            self.create_point_meta_table(meta_name=meta)
        for meta in self.point_meta_str_tables:
            self.create_point_meta_table(meta_name=meta)
    
    def create_all_views(self) -> None:
        for aggregate_name in ('daily',
                               'monthly',
                               'yearly',
                               'hourly',
                               'aq_data'):
            for approval_level in self.where_clauses:
                self.create_aggregate_view(aggregate_name,
                                           approval_level.capitalize())
    
    def create_daily_aggregate_table(self) -> None:
        self.create_aggregate_table()
        
    def create_monthly_aggregate_table(self) -> None:
        self.create_aggregate_table(aggregate_name='monthly')
    
    def create_real_time_table(self) -> None:
        self.create_aggregate_table(aggregate_name='aq_data')
    
    def create_all_tables_and_triggers(self) -> None:
        self.create_aggregate_tables()
        self.create_point_meta_tables()
        self.create_all_triggers()
        
    def create_all_tables_triggers_and_views(self) -> None:
        self.create_all_tables_and_triggers()
        self.create_all_views()
        
    #===========================================================================
    # INSERT , SELECT DELETE METHODS
    #===========================================================================
    def insert_into_aggregate_table(self, timeseries_uniqueid: str ,
                                    station_identifier: str=None,
                                    station_id: int=None,
                                    points: Sequence=None,
                                    aggregate_name: str='daily') -> None:
        """
        @param points: should be a list of point objects 
                       with a get_insert_tuple method that returns the correct fields.
                       If the points come from the operational pollign this is already the case.
        """
        table_name: str = self.get_table_name(aggregate_name)
        
        def yield_insert_tuple_from_points() -> Sequence[str,
                                                         datetime,
                                                         float,
                                                         int,
                                                         str,
                                                         Sequence[int],
                                                         Sequence[str]]:
            t: tuple[str] = (timeseries_uniqueid,)
            for pt in points:
                t_pt = pt.get_insert_tuple()
                if t_pt:
                    insert_tuple = [*t,
                                  *t_pt
                                 ]
                    yield tuple(insert_tuple)
                             
        with self.connect() as con:
            sql = f"""
              INSERT INTO 
                  {table_name}(timeseries_uniqueid,
                               value_timestamp,
                               value,
                               approval,
                               grade,
                               qualifiers,
                               qualifierCodes)
              VALUES(?,?,?,?,?,?,?)
              ON CONFLICT DO UPDATE 
                  SET 
                      value=excluded.value,
                      approval=excluded.approval,
                      grade=excluded.grade,
                      qualifiers=excluded.qualifiers,
                      qualifierCodes=excluded.qualifierCodes
                  ;
              """
            con.executemany(sql, yield_insert_tuple_from_points())
    
    def delete_from_aggregate_table(self,
                                    ts_unique_id_and_timestamp: List[Tuple[str, datetime]],
                                    aggregate_name: str='daily') -> None:
        table_name: str = self.get_table_name(aggregate_name)
        with self.connect() as con:
            sql = f"""
                  DELETE FROM 
                      {table_name}
                  WHERE
                      timeseries_uniqueid=?
                  AND
                      value_timestamp=?
                  """
            con.executemany(sql, tuple(ts_unique_id_and_timestamp))
    
    def get_aggregate_table_data(self,
                                 timeseries_uniqueid: str,
                                 query_from: datetime=None,
                                 query_to: datetime=None,
                                 aggregate_name: str='daily') -> sqlite3.Cursor:
        
        table_name: str = self.get_table_name(aggregate_name)
        params = [timeseries_uniqueid]
        where_clause_and = ''
        with self.connect() as con:
            if query_from and query_to:
                where_clause_and = f"""
                                   AND
                                   value_timestamp BETWEEN ? and ?
                                   """
                params.extend((query_from, query_to))
            elif query_from is not None:
                where_clause_and = f"""
                                   AND
                                   value_timestamp >= ?
                                   """
                params.append(query_from)
            elif query_to is not None:
                where_clause_and = f"""
                                   AND
                                   value_timestamp <= ?
                                   """
                params.append(query_to)
            sql = f"""
                  SELECT 
                      value_timestamp,
                      value,
                      approval,
                      grade,
                      qualifiers,
                      qualifierCodes
                  FROM 
                      {table_name}
                  WHERE
                      timeseries_uniqueid = ?
                  {where_clause_and}
                  ORDER BY
                  value_timestamp
                  """
            return con.execute(sql, tuple(params))

        
@dataclass 
class ForecastMinimalGeometryDBUtil(SQLiteWithStationAndTrigger,
                                    SQLiteJSONGeometryType):
    """
    Class to create the minimal stations and their location and basin geometry
    """
    
    def __post_init__(self) -> None:
        self.forecast_station_name = 'ForecastStation'
        self.forecast_basin_name = 'ForecastBasin'
        super().__post_init__()
        
    def create_forecast_station_table(self) -> None:
        with self.connect() as con:
            sql = f"""
                  CREATE TABLE IF NOT EXISTS {self.forecast_station_name}(
                      station_id INTEGER PRIMARY KEY REFERENCES Station(id),
                      latitude REAL,
                      longitude REAL,
                      geometry {self.geometry_type}
                  )
                  """
            con.execute(sql)
            
    def create_forecast_basin_table(self) -> None:
        with self.connect() as con:
            sql = f"""
                  CREATE TABLE IF NOT EXISTS {self.forecast_basin_name}(
                      station_id INTEGER PRIMARY KEY REFERENCES Station(id),
                      geometry {self.geometry_type}
                  )
                  """
            con.execute(sql)
    
    #===========================================================================
    # TRIGGERS
    #===========================================================================
    def create_forecast_station_changes_table(self) -> None:
        with self.connect() as con:
            sql = f"""
                  CREATE TABLE IF NOT EXISTS ForecastStationChanges(
                      station_id INTEGER REFERENCES Station(id),
                      time_of_change TIMESTAMP,
                      old_latitude REAL,
                      new_latitude REAL,
                      old_longitude REAL,
                      new_longitude REAL,
                      old_geometry {self.geometry_type},
                      new_geometry {self.geometry_type},
                      PRIMARY KEY (station_id,time_of_change)
                  )
                  """
            con.execute(sql)
            
    def create_forecast_basin_changes_table(self) -> None:
        with self.connect() as con:
            sql = f"""
                  CREATE TABLE IF NOT EXISTS ForecastBasinChanges(
                      station_id INTEGER REFERENCES Station(id),
                      time_of_change TIMESTAMP,
                      old_geometry {self.geometry_type},
                      new_geometry {self.geometry_type},
                      PRIMARY KEY (station_id,time_of_change) 
                  )
                  """
            con.execute(sql)
            
    def create_forecast_station_update_trigger(self) -> None:
        with self.connect() as con:
            sql = f"""
                  CREATE TRIGGER IF NOT EXISTS log_ForecastBasinChanges_UPDATE
                  AFTER UPDATE
                  ON ForecastBasin
                  WHEN (SELECT triggers_are_on FROM TriggerStatus)=1
                  BEGIN
                  INSERT INTO
                      ForecastBasinChanges(station_id,
                                           changes_timestamp,
                                           old_geometry,
                                           new_geometry
                                          )
                  VALUES(new.station_id,
                         CURRENT_TIMESTAMP,
                         old.geometry,
                         new.geometry
                         );
                  END;
                  """
            con.execute(sql)
    
    def create_forecast_basin_update_trigger(self) -> None:
        with self.connect() as con:
            sql = f"""
                  CREATE TRIGGER IF NOT EXISTS log_ForecastStationChanges_UPDATE
                  AFTER UPDATE
                  ON ForecastStation
                  WHEN (SELECT triggers_are_on FROM TriggerStatus)=1
                  BEGIN
                  INSERT INTO
                      ForecastStationChanges(station_id,
                                             time_of_change,
                                             old_latitude,
                                             new_latitude,
                                             old_longitude,
                                             new_longitude,
                                             old_geometry,
                                             new_geometry
                                            )
                  VALUES(new.station_id,
                         CURRENT_TIMESTAMP,
                         old.latitude,
                         new.latitude,
                         new.longitude,
                         old.longitude,
                         old.geometry,
                         new.geometry
                         );
                  END;
                  """
            con.execute(sql)
            
    def insert_station_location(self,
                             station_id: int=None,
                             station_identifier: str=None,
                             latitude: float=None,
                             longitude: float=None,
                             geometry: str=None) -> None:
        """
        Assuming the geometry is GeoJSON
        """
        with self.connect() as con:
            if station_id is None and station_identifier: 
                station_id = self.get_station_id_from_identifier(station_identifier)
            geom = self.get_station_location_geojson_from_station_id(station_id)
            if geom != geometry:
                # Upsert ok
                geo_insert_sql = self.get_geom_insert_sql(geometry)
                sql = f"""INSERT INTO
                            {self.forecast_station_name}(station_id,
                                                         latitude,
                                                         longitude,
                                                         geometry
                                                        )
                          VALUES(station_id,
                                 latitude,
                                 longitude,
                                 {geo_insert_sql})
                          ON CONFLICT DO UPDATE
                          SET 
                              latitude=excluded.latitude
                              longitude=excluded.longitude
                              geometry=excluded.geometry
                      ;
                  """
    
    def insert_station_basin(self,
                             station_id: int=None,
                             station_identifier: str=None,
                             geometry: str=None) -> None:
        """
        Assuming the geometry is GeoJSON
        """
        with self.connect() as con:
            if station_id is None and station_identifier: 
                station_id = self.get_station_id_from_identifier(station_identifier)
            geom = self.get_station_location_geojson_from_station_id(station_id)
            if geom != geometry:
                # Upsert ok, not there or not the same geometry
                geo_insert_sql = self.get_geom_insert_sql(geometry)
                sql = f"""INSERT INTO
                            {self.forecast_basin_name}(station_id,
                                                       geometry
                                                      )
                          VALUES(station_id,
                                 {geo_insert_sql})
                          ON CONFLICT DO UPDATE
                          SET 
                              geometry=excluded.geometry
                      ;
                  """      
            
    def create_forecast_geometry_tables(self) -> None:
        self.create_forecast_station_table()
        self.create_forecast_basin_table()
        self.create_forecast_basin_changes_table()
        self.create_forecast_station_changes_table()
        
    def create_forecast_geometry_triggers(self) -> None:
        self.create_forecast_basin_update_trigger()
        self.create_forecast_station_update_trigger()
        
    def create_forecast_geometry_tables_and_triggers(self) -> None:
        self.create_station_table()
        self.create_forecast_geometry_tables()
        self.create_forecast_geometry_triggers()

        
@dataclass 
class ForecastDBUtil(ForecastMinimalGeometryDBUtil):
    """
    In order to avoid external dependencies:
    - SQLite is used
    - Assuming geometries will be stored as geojson (text)
    Also of note if dependencies are not an issue:
    - As of SQLite version 3.38.0 (2022-02-22) the JSON functions and operators are built into SQLite by default
        - As of 2022-03-01 Many python distribution may not have this version available
        - Use of the JSON-specific functions will be avoided for this first version
    - For a complete OGC compliant geometry/topology DBMS package, consider using Spatialite
    If opting to make this class PostgreSQl-friendly
    - Consider using POSTGIS, this would enabled GIS-level manipulations of rasters, vectors and topologies directly from DB queries
      as well as support for many formats.
    """
    
    def __post_init__(self) -> None:
        # self.forecast_station_name = 'ForecastStation'
        # self.forecast_basin_name = 'ForecastBasin'
        super().__post_init__()
    
    #===========================================================================
    # BASE TABLES
    #===========================================================================
    def create_forecast_time_series_table(self) -> None:
        with self.connect() as con:
            sql = """
                  CREATE TABLE IF NOT EXISTS ForecastTimeSeries(
                      station_id INTEGER REFERENCES Station(id),
                      file_creation_time TIMESTAMP,
                      model TEXT,
                      step_0_timestamp TIMESTAMP,
                      run INTEGER,
                      step INTEGER,
                      forecast_timestamp TIMESTAMP,
                      forecast_value REAL,
                      PRIMARY KEY (station_id,model,step_0_timestamp,run,step)
                  )
                  """
            con.execute(sql)
    
    #===========================================================================
    # SELECT AND INSERT
    #===========================================================================
    def add_and_where_clause(self,
                             where_clause: str,
                             new_statement: str) -> str:
        if where_clause:
            return ''.join((where_clause_and,
                            '\nAND\n\t',
                            new_statement
                          ))
        else:
            return ''.join(('\nAND\n\t', new_statement))
        
    def get_where_clause_for_select(self,
                                    file_creation_time: datetime=None,
                                    query_from: datetime=None,
                                    query_to: datetime=None,
                                    step_0_timestamp: datetime=None,
                                    run: int=None,
                                    step: int=None,
                                    forecast_timestamp=None) -> Tuple[str,
                                                             List[Union[str,
                                                                        datetime,
                                                                        int
                                                                       ]
                                                                 ]
                                                            ]:
        
        where_clause = ''
        if file_creation_time:
            where_clause = self.add_and_where_clause(where_clause,
                                                     'file_creation_time = ?'
                                                    )
            params.append(file_creation_time)
            
        if query_from and query_to:
            where_clause = self.add_and_where_clause(where_clause,
                                                     'value_timestamp BETWEEN ? and ?'
                                                    )   
            params.extend((query_from, query_to))
        elif query_from is not None:
            where_clause = self.add_and_where_clause(where_clause,
                                                     'value_timestamp >= ?'
                                                    )
            params.append(query_from)
        elif query_to is not None:
            where_clause = self.add_and_where_clause(where_clause,
                                                     'value_timestamp <= ?'
                                                    )
            params.append(query_to)
        if step_0_timestamp:
            where_clause = self.add_and_where_clause(where_clause,
                                                     'step_0_timestamp = ?'
                                                    )
            params.append(step_0_timestamp)
        if run:
            where_clause = self.add_and_where_clause(where_clause,
                                                     'run = ?'
                                                     )
            params.append(run)
        if step:
            where_clause = self.add_and_where_clause(where_clause,
                                                     'step = ?'
                                                     )
            params.append(step)
        if forecast_timestamp:
            where_clause = self.add_and_where_clause(where_clause,
                                                     'step = ?'
                                                     )
            params.append(forecast_timestamp)
        
        return where_clause, params
        
    def get_forecast_data(self,
                          station_identifier: Union[str, List[str]],
                          station_id: Union[str, List[str]],
                          file_creation_time: datetime=None,
                          query_from: datetime=None,
                          query_to: datetime=None,
                          step_0_timestamp: datetime=None,
                          run: int=None,
                          step: int=None,
                          forecast_timestamp=None,
                          ) -> sqlite3.Cursor:
        """
        Selection per allowed based on:
        - step
        - run
        - step0 date and time
        - forecast time interval
        - exact forecast time
        """
        station_id = self.get_station_id_in_clause_from_identifiers_and_ids(station_identifier,
                                                                            station_id)
                              
        where_clause, params = self.get_where_clause_for_select(file_creation_time,
                                                               query_from,
                                                               query_to,
                                                               step_0_timestamp,
                                                               run,
                                                               step,
                                                               forecast_timestamp)
        with self.connect() as con:
            sql = f"""
                  SELECT 
                      *
                  FROM 
                      ForecastTimeSeries
                  WHERE
                      station_id IN ({station_id})
                  {where_clause}
                  ORDER BY
                      forecast_timestamp
                  """
            return con.execute(sql,
                               tuple(params))
        
    def insert_forecast_data(self,
                             insert_iterator: Iterable[Sequence[int,
                                                                 datetime,
                                                                 datetime,
                                                                 int,
                                                                 int,
                                                                 datetime,
                                                                 float]
                                                        ]) -> None:
        """
        - Assuming the data is a iterator of tuple
        - Assuming the tuples are of the form 
        (station_id,
        file_creation_time,
        step_0_timestamp,
        run,
        step,
        forecast_timestamp,
        forecast_value
        )
        ***Note:
        The insert operation is actually an upsert, not an "insert or update"
        """

        def get_iter() -> Tuple[int,
                                datetime,
                                datetime,
                                int,
                                int,
                                datetime,
                                float]:
            """
            Making sure we send the correct data format to the executemany command
            """
            for t_insert in insert_iterator:
                yield tuple(t_insert)
        
        with self.connect() as con:
            sql = """
                  INSERT INTO 
                  ForecastTimeSeries(station_id,
                                     file_creation_time,
                                     step_0_timestamp,
                                     run,
                                     step,
                                     forecast_timestamp,
                                     forecast_value
                                    )
                  VALUES(?,?,?,?,?,?,?)
                  ON CONFLICT DO UPDATE
                      SET 
                          forecast_timestamp=excluded.forecast_timestamp
                          forecast_value=excluded.forecast_value
                      ;
                  """
            con.executemany(sql,
                            get_iter())
        
    def create_tables(self) -> None:
        self.create_forecast_time_series_table()
        
    def create_tables_and_triggers(self) -> None:
        self.create_forecast_geometry_tables_and_triggers()
        self.create_tables()

        
if __name__ == "__main__":
    import os
    test_aquarius_data = AquariusDataDBUtil(db_file_path='D:/Flow Prediction/AquariusData.sqlite3')
    test_aquarius_data.create_all_tables_triggers_and_views()
    test_forecast_data = ForecastDBUtil(db_file_path='D:/Flow Prediction/Forecasts.sqlite3')
    test_forecast_data.create_tables_and_triggers()
    test_minimal_geom = ForecastMinimalGeometryDBUtil(db_file_path='D:/Flow Prediction/ForecastsMinimalGeom.sqlite3')
    test_minimal_geom.create_forecast_geometry_tables_and_triggers()
