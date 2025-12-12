# -*- coding: utf-8 -*-
"""Additional Artists Details
"""
# Copyright (C) 2023-2025 Bob Swift (rdswift)
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

# pylint: disable=line-too-long
# pylint: disable=import-error
# pylint: disable=too-many-arguments
# pylint: disable=too-many-locals


from collections import namedtuple
from functools import partial
from typing import Callable

from picard.plugin3.api import (
    OptionsPage,
    PluginApi,
)
from picard.webservice.api_helpers import MBAPIHelper

from .ui_options_additional_artists_details import (
    Ui_AdditionalArtistsDetailsOptionsPage,
)


USER_GUIDE_URL = 'https://picard-plugins-user-guides.readthedocs.io/en/latest/additional_artists_variables/user_guide.html'

# Named tuples for code clarity
Area = namedtuple('Area', ['parent', 'name', 'country', 'type', 'type_text'])
MetadataPair = namedtuple('MetadataPair', ['artists', 'target'])

# MusicBrainz ID codes for relationship types
RELATIONSHIP_TYPE_PART_OF = 'de7cc874-8b1b-3a05-8272-f3834c968fb7'

# MusicBrainz ID codes for area types
AREA_TYPE_COUNTRY = '06dd0ae4-8c74-30bb-b43d-95dcedf961de'
AREA_TYPE_COUNTY = 'bcecec27-8bdb-3e00-8254-d948dda502fa'
AREA_TYPE_MUNICIPALITY = '17246454-5ac4-36a1-b81a-4753eb2dab20'
AREA_TYPE_SUBDIVISION = 'fd3d44c5-80a1-3842-9745-2c4972d35afa'

CONDITIONAL_LOCATIONS = {AREA_TYPE_COUNTY, AREA_TYPE_MUNICIPALITY, AREA_TYPE_SUBDIVISION}

# Standard text for arguments
ALBUM_ARTISTS = 'album_artists'
ARTIST = 'artist'
ARTIST_REQUESTS = 'artist_requests'
AREA = 'area'
AREA_REQUESTS = 'area_requests'
ISO_CODES_1 = 'iso-3166-1-codes'
ISO_CODES_2 = 'iso-3166-2-codes'
OPT_AREA_COUNTY = 'aad_area_county'
OPT_AREA_MUNICIPALITY = 'aad_area_municipality'
OPT_AREA_SUBDIVISION = 'aad_area_subdivision'
OPT_PROCESS_TRACKS = 'aad_process_tracks'
TRACKS = 'tracks'

PLUGIN_NAME = "Additional Artists Details"


class CustomHelper(MBAPIHelper):
    """Custom MusicBrainz API helper to retrieve artist and area information.
    """

    def get_artist_by_id(self, _id: str, handler: Callable, inc: list = None, priority: bool = False, important:bool = False,
                         mblogin: bool = False, refresh: bool = False):
        """Get information for the specified artist MBID.

        Args:
            _id (str): Artist MBID to retrieve.
            handler (Callable): Callback used to process the returned information.
            inc (list, optional): List of includes to add to the API call. Defaults to None.
            priority (bool, optional): Process the request at a high priority. Defaults to False.
            important (bool, optional): Identify the request as important. Defaults to False.
            mblogin (bool, optional): Request requires logging into MusicBrainz. Defaults to False.
            refresh (bool, optional): Request triggers a refresh. Defaults to False.

        Returns:
            RequestTask: Requested task object.
        """
        return self._get_by_id(ARTIST, _id, handler, inc, priority=priority, important=important, mblogin=mblogin, refresh=refresh)

    def get_area_by_id(self, _id: str, handler: Callable, inc: list = None, priority: bool = False, important: bool = False,
                       mblogin: bool = False, refresh: bool = False):
        """Get information for the specified area MBID.

        Args:
            _id (str): Area MBID to retrieve.
            handler (Callable): Callback used to process the returned information.
            inc (list, optional): List of includes to add to the API call. Defaults to None.
            priority (bool, optional): Process the request at a high priority. Defaults to False.
            important (bool, optional): Identify the request as important. Defaults to False.
            mblogin (bool, optional): Request requires logging into MusicBrainz. Defaults to False.
            refresh (bool, optional): Request triggers a refresh. Defaults to False.

        Returns:
            RequestTask: Requested task object.
        """
        if inc is None:
            inc = ['area-rels']
        return self._get_by_id(AREA, _id, handler, inc, priority=priority, important=important, mblogin=mblogin, refresh=refresh)


class ArtistDetailsPlugin:
    """Plugin to retrieve artist details, including area and country information.
    """

    # Area types to exclude from the location string
    EXCLUDE_AREA_TYPES = {AREA_TYPE_MUNICIPALITY, AREA_TYPE_COUNTY, AREA_TYPE_SUBDIVISION}

    result_cache = {
        ARTIST: {},
        ARTIST_REQUESTS: set(),
        AREA: {},
        AREA_REQUESTS: set(),
    }
    album_processing_count = {}
    albums = {}
    album_area_requests: dict[str, set] = {}

    def __init__(self, api: PluginApi):
        self.api = api

    def _add_album_area_request(self, album_id: str, area_id: str):
        if album_id not in self.album_area_requests:
            self.album_area_requests[album_id] = set()
        self.album_area_requests[album_id].add(area_id)

    def _remove_album_area_request(self, album_id: str, area_id: str):
        if album_id in self.album_area_requests:
            self.album_area_requests[album_id].discard(area_id)

    def _get_album_area_request_count(self, album_id: str):
        if album_id not in self.album_area_requests:
            return 0
        return len(self.album_area_requests[album_id])

    def _make_empty_target(self, album_id: str):
        """Create an empty album target node if it doesn't exist.

        Args:
            album_id (str): MBID of the album.
        """
        if album_id not in self.albums:
            self.albums[album_id] = {ALBUM_ARTISTS: set(), TRACKS: []}

    def _add_target(self, album_id: str, artists: set, target_metadata: PluginApi.Metadata):
        """Add a metadata target to update for an album.

        Args:
            album_id (str): MBID of the album.
            artists (set): Set of artists to include.
            target_metadata (api.Metadata): Target metadata to update.
        """
        self._make_empty_target(album_id)
        self.albums[album_id][TRACKS].append(MetadataPair(artists, target_metadata))

    def _remove_album(self, album_id: str):
        """Removes an album from the metadata processing dictionary.

        Args:
            album_id (str): MBID of the album to remove.
        """
        self.api.logger.debug("Removing album '%s'", album_id)
        self.albums.pop(album_id, None)
        self.album_processing_count.pop(album_id, None)

    def _album_add_request(self, album: PluginApi.Album):
        """Increment the number of pending requests for an album.

        Args:
            album (api.Album): The Album object to use for the processing.
        """
        if album.id not in self.album_processing_count:
            self.album_processing_count[album.id] = 0
        self.album_processing_count[album.id] += 1
        # album._requests += 1

    def _album_remove_request(self, album: PluginApi.Album):
        """Decrement the number of pending requests for an album.

        Args:
            album (api.Album): The Album object to use for the processing.
        """
        if album.id not in self.album_processing_count:
            self.album_processing_count[album.id] = 1
        self.album_processing_count[album.id] -= 1
        # album._requests -= 1
        if self._get_album_area_request_count(album.id) < 1:
            self._save_artist_metadata(album.id)
            album._finalize_loading(None)   # pylint: disable=protected-access

    def remove_album(self, _api: PluginApi, album: PluginApi.Album):
        """Remove the album from the albums processing dictionary.

        Args:
            _api (PluginApi): The plugin API object.
            album (api.Album): The album object to remove.
        """
        self._remove_album(album.id)

    def make_album_vars(self, _api: PluginApi, album: PluginApi.Album, album_metadata, _release_metadata: dict):
        """Process album artists.

        Args:
            _api (PluginApi): The plugin API object.
            album (api.Album): The Album object to use for the processing.
            album_metadata (api.Metadata): Metadata object for the album.
            _release_metadata (dict): Dictionary of release data from MusicBrainz api.
        """
        artists = set(artist.id for artist in album.get_album_artists())
        self._make_empty_target(album.id)
        self.albums[album.id][ALBUM_ARTISTS] = artists
        if not self.api.plugin_config[OPT_PROCESS_TRACKS]:
            self.api.logger.info("Track artist processing is disabled.")
        self._artist_processing(artists, album, album_metadata, 'Album')

    def make_track_vars(self, _api: PluginApi, album: PluginApi.Album, album_metadata: PluginApi.Metadata,
                        track_metadata: dict, _release_metadata: dict):
        """Process track artists.

        Args:
            _api (PluginApi): The plugin API object.
            album (api.Album): The Album object to use for the processing.
            album_metadata (api.Metadata): Metadata object for the album.
            track_metadata (dict): Dictionary of track data from MusicBrainz api.
            _release_metadata (dict): Dictionary of release data from MusicBrainz api.
        """
        artists = set()
        source_type = 'track'
        # Test for valid metadata node.
        # The 'artist-credit' key should always be there.
        # This check is to avoid a runtime error if it doesn't exist for some reason.
        if self.api.plugin_config[OPT_PROCESS_TRACKS]:
            if 'artist-credit' in track_metadata:
                for artist_credit in track_metadata['artist-credit']:
                    if 'artist' in artist_credit:
                        if 'id' in artist_credit['artist']:
                            artists.add(artist_credit['artist']['id'])
                    else:
                        # No 'artist' specified.  Log as an error.
                        self._metadata_error(album.id, 'artist-credit.artist', source_type)
            else:
                # No valid metadata found.  Log as error.
                self._metadata_error(album.id, 'artist-credit', source_type)
        self._artist_processing(artists, album, album_metadata, 'Track')

    def _artist_processing(self, artists: set, album: PluginApi.Album, destination_metadata: PluginApi.Metadata, source_type: str):
        """Retrieves the information for each artist not already processed.

        Args:
            artists (set): Set of artist MBIDs to process.
            album (api.Album): Album object to use for the processing.
            destination_metadata (api.Metadata): Metadata object to update with the new variables.
            source_type (str): Source type (album or track) for logging messages.
        """
        for temp_id in artists:
            if temp_id not in self.result_cache[ARTIST_REQUESTS]:
                self.result_cache[ARTIST_REQUESTS].add(temp_id)
                self.api.logger.debug('Retrieving artist ID %s information from MusicBrainz.', temp_id)
                self._get_artist_info(temp_id, album)
            else:
                self.api.logger.debug('%s artist ID %s information available from cache.', source_type, temp_id)
        self._add_target(album.id, artists, destination_metadata)
        self._save_artist_metadata(album.id)

    def _save_artist_metadata(self, album_id: str):
        """Saves the new artist details variables to the metadata targets for the specified album.

        Args:
            album_id (str): MBID of the album to process.
        """
        if album_id in self.album_processing_count and self.album_processing_count[album_id]:
            return
        if self._get_album_area_request_count(album_id) > 0:
            return
        if album_id not in self.albums or not self.albums[album_id][TRACKS]:
            self.api.logger.error("No metadata targets found for album '%s'", album_id)
            return
        for item in self.albums[album_id][TRACKS]:
            # Add album artists to track so they are available in the metadata
            artists = self.albums[album_id][ALBUM_ARTISTS].copy().union(item.artists)
            destination_metadata = item.target
            for artist in artists:
                if artist in self.result_cache[ARTIST]:
                    self._set_artist_metadata(destination_metadata, artist, self.result_cache[ARTIST][artist])

    def _set_artist_metadata(self, destination_metadata: PluginApi.Metadata, artist_id: str, artist_info: dict):
        """Adds the artist information to the destination metadata.

        Args:
            destination_metadata (api.Metadata): Metadata object to update with new variables.
            artist_id (str): MBID of the artist to update.
            artist_info (dict): Dictionary of information for the artist.
        """
        def _set_item(key, value):
            destination_metadata[f"~artist_{artist_id}_{key.replace('-', '_')}"] = value

        for item in artist_info.keys():
            if item in {'area', 'begin-area', 'end-area'}:
                country, location = self._drill_area(artist_info[item])
                if country:
                    _set_item(item.replace('area', 'country'), country)
                if location:
                    _set_item(item.replace('area', 'location'), location)
            else:
                _set_item(item, artist_info[item])

    def _get_artist_info(self, artist_id: str, album: PluginApi.Album):
        """Gets the artist information from the MusicBrainz website.

        Args:
            artist_id (str): MBID of the artist to retrieve.
            album (api.Album): The Album object to use for the processing.
        """
        self._album_add_request(album)
        helper = CustomHelper(album.tagger.webservice)
        handler = partial(
            self._artist_submission_handler,
            artist=artist_id,
            album=album,
        )
        # return helper.get_artist_by_id(artist_id, handler)
        return self.api.add_album_task(
            album=album,
            task_id=f"Artist={artist_id}",
            description=f"Get info for artist: {artist_id}",
            timeout=10.,
            request_factory=lambda: helper.get_artist_by_id(artist_id, handler)
        )

    def _artist_submission_handler(self, document, _reply, error, artist=None, album=None):
        """Handles the response from the webservice requests for artist information.
        """
        try:
            if error:
                self.api.logger.error("Artist '%s' information retrieval error.", artist)
                return
            artist_info = {}
            for item in ['type', 'gender', 'name', 'sort-name', 'disambiguation']:
                if item in document and document[item]:
                    artist_info[item] = document[item]
            if 'life-span' in document:
                for item in ['begin', 'end']:
                    if item in document['life-span'] and document['life-span'][item]:
                        artist_info[item] = document['life-span'][item]
            for item in ['area', 'begin-area', 'end-area']:
                if item in document and document[item] and 'id' in document[item] and document[item]['id']:
                    area_id = document[item]['id']
                    artist_info[item] = area_id
                    if area_id not in self.result_cache[AREA_REQUESTS]:
                        self._get_area_info(area_id, album)
            self.result_cache[ARTIST][artist] = artist_info
        finally:
            self._album_remove_request(album)

    def _get_area_info(self, area_id, album: PluginApi.Album):
        """Gets the area information from the MusicBrainz website.

        Args:
            area_id (str): MBID of the area to retrieve.
            album (api.Album): The Album object to use for the processing.
        """
        self.result_cache[AREA_REQUESTS].add(area_id)
        self._album_add_request(album)
        self._add_album_area_request(album.id, area_id)
        self.api.logger.debug('Retrieving area ID %s from MusicBrainz.', area_id)
        helper = CustomHelper(album.tagger.webservice)
        handler = partial(
            self._area_submission_handler,
            area=area_id,
            album=album,
        )
        # return helper.get_area_by_id(area_id, handler)
        return self.api.add_album_task(
            album=album,
            task_id=f"Area={area_id}",
            description=f"Get info for area: {area_id}",
            timeout=10.,
            request_factory=lambda: helper.get_area_by_id(area_id, handler)
        )

    def _area_submission_handler(self, document, _reply, error, area=None, album=None):
        """Handles the response from the webservice requests for area information.
        """
        try:
            if error:
                self.api.logger.error("Area '%s' information retrieval error.", area)
                return
            (_id, name, country, _type, type_text) = self._parse_area(document)
            if _type == AREA_TYPE_COUNTRY and _id not in self.result_cache[AREA]:
                self._area_logger(_id, f"{name} ({country})", type_text)
                self.result_cache[AREA][_id] = Area('', name, country, _type, type_text)
            if 'relations' in document:
                for rel in document['relations']:
                    self._parse_area_relation(_id, rel, album, name, _type, type_text)
        finally:
            self._remove_album_area_request(album.id, area)
            self._album_remove_request(album)

    def _area_logger(self, area_id: str, area_name: str, area_type: str):
        """Adds a log entry for the area retrieved.

        Args:
            area_id (str): MBID of the area added.
            area_name (str): Name of the area added.
            area_type (str): Type of area added.
        """
        self.api.logger.debug("Adding area: %s => %s of type '%s'", area_id, area_name, area_type)

    def _parse_area_relation(self, area_id: str, area_relation: dict, album: PluginApi.Album, area_name: str,
                             area_type: str, area_type_text: str):
        """Parse an area relation to extract the area information.

        Args:
            area_id (str): MBID of the area providing the relationship.
            area_relation (dict): Dictionary of the area relationship.
            album (api.Album): The Album object to use for the processing.
            area_name (str): Name of the area providing the relationship.
            area_type (str): MBID of the type of area providing the relationship.
            area_type_text (str): Text description of the area providing the relationship.
        """
        if 'type-id' not in area_relation or 'area' not in area_relation or area_relation['type-id'] != RELATIONSHIP_TYPE_PART_OF:
            return
        (_id, name, country, _type, type_text) = self._parse_area(area_relation['area'])
        if not _id:
            return

        def _add_country(_id, name, country, _type, type_text):
            if _id not in self.result_cache[AREA]:
                self._area_logger(_id, f"{name} ({country})", type_text)
                self.result_cache[AREA][_id] = Area('', name, country, _type, type_text)
                self.result_cache[AREA_REQUESTS].add(_id)

        if 'direction' in area_relation and area_relation['direction'] == 'backward':
            if area_id not in self.result_cache[AREA]:
                self._area_logger(area_id, area_name, area_type_text)
                self.result_cache[AREA][area_id] = Area(_id, area_name, '', area_type, type_text)
                self.result_cache[AREA_REQUESTS].add(area_id)
            if _type == AREA_TYPE_COUNTRY:
                _add_country(_id, name, country, _type, type_text)
            else:
                if _id not in self.result_cache[AREA] and _id not in self.result_cache[AREA_REQUESTS]:
                    self._get_area_info(_id, album)

        elif 'direction' in area_relation and area_relation['direction'] == 'forward' and _type == AREA_TYPE_COUNTRY:
            _add_country(_id, name, country, _type, type_text)

        else:
            self._area_logger(_id, name, type_text)
            self.result_cache[AREA_REQUESTS].add(_id)
            self.result_cache[AREA][_id] = Area(area_id, name, '', _type, type_text)

    @staticmethod
    def _parse_area(area_info: dict) -> tuple[str, str, str, str, str]:
        """Parse a dictionary of area information to return selected elements.

        Args:
            area_info (dict): Area information to parse.

        Returns:
            tuple: Selected information for the area (id, name, country code, type code, type text).
        """
        if 'id' not in area_info:
            return ('', '', '', '', '')
        area_id = area_info['id']
        area_name = area_info['name'] if 'name' in area_info else 'Unknown Name'
        area_type = area_info['type-id'] if 'type-id' in area_info else ''
        area_type_text = area_info['type'] if 'type' in area_info else 'Unknown Area Type'
        country = ''
        if area_type == AREA_TYPE_COUNTRY:
            if ISO_CODES_1 in area_info and area_info[ISO_CODES_1]:
                country = area_info[ISO_CODES_1][0]
            elif ISO_CODES_2 in area_info and area_info[ISO_CODES_2]:
                country = area_info[ISO_CODES_2][0][:2]
        return (area_id, area_name, country, area_type, area_type_text)

    def _metadata_error(self, album_id: str, metadata_element: str, metadata_group: str):
        """Logs metadata-related errors.

        Args:
            album_id (str): MBID of the album being processed.
            metadata_element (str): Metadata element initiating the error.
            metadata_group (str): Metadata group initiating the error.
        """
        self.api.logger.error("Album '%s' missing '%s' in %s metadata.", album_id, metadata_element, metadata_group)

    def _drill_area(self, area_id: str) -> tuple[str, str]:
        """Drills up from the specified area to determine the two-character
        country code and the full location description for the area.

        Args:
            area_id (str): MBID of the area to process.

        Returns:
            tuple: The two-character country code and full location description for the area.
        """
        # pylint: disable=too-many-boolean-expressions
        country = ''
        location = []
        i = 7   # Counter to avoid potential runaway processing
        while i and area_id and not country:
            i -= 1
            area = self.result_cache[AREA][area_id] if area_id in self.result_cache[AREA] else Area('', '', '', '', '')
            country = area.country
            area_id = area.parent
            if not location or area.type not in CONDITIONAL_LOCATIONS:
                location.append(area.name)
            else:
                if (
                    (area.type == AREA_TYPE_COUNTY and self.api.plugin_config[OPT_AREA_COUNTY])
                    or (area.type == AREA_TYPE_MUNICIPALITY and self.api.plugin_config[OPT_AREA_MUNICIPALITY])
                    or (area.type == AREA_TYPE_SUBDIVISION and self.api.plugin_config[OPT_AREA_SUBDIVISION])
                ):
                    location.append(area.name)
        return country, ', '.join(location)


class AdditionalArtistsDetailsOptionsPage(OptionsPage):
    """Options page for the Additional Artists Details plugin.
    """

    NAME = "additional_artists_details"
    TITLE = "Additional Artists Details"
    PARENT = "plugins"

    def __init__(self, parent=None):
        super(AdditionalArtistsDetailsOptionsPage, self).__init__(parent)
        self.TITLE = self.api.tr('options.page_title', "Additional Artists Details")

        self.ui = Ui_AdditionalArtistsDetailsOptionsPage()
        self.ui.setupUi(self)

        # Add translations
        self.ui.gb_description.setTitle(self.api.tr("ui.gb_description", "Additional Artists Details"))
        self.ui.format_description.setText(
            self.api.tr(
                "ui.format_description",
                (
                    "<html><head/><body><p>These settings will determine how the <span style=\" font-weight:600;\">Additional "
                    "Artists Details</span> plugin operates.</p><p>Please see the <a href=\"{url}\"><span style=\" text-decoration: "
                    "underline; color:#0000ff;\">User Guide</span></a> for additional information.</p></body></html>"
                )
            ).format(url=USER_GUIDE_URL)
        )
        self.ui.gb_process_track_artists.setTitle(self.api.tr("ui.gb_process_track_artists", "Process Track Artists"))
        self.ui.label.setText(
            self.api.tr(
                "ui.label_track_artists",
                (
                    "<html><head/><body><p>This option determines whether or not details are retrieved for all track artists on the "
                    "release. If you are only interested in details for the album artists then this should be disabled, thus "
                    "significantly reducing the number of additional calls made to the MusicBrainz api and reducing the time required "
                    "to load a release. Album artists are always processed.</p></body></html>"
                )
            )
        )
        self.ui.cb_process_tracks.setText(self.api.tr("ui.cb_process_tracks", "Process track artists"))
        self.ui.gb_area_details.setTitle(self.api.tr("ui.gb_area_details", "Include Area Details"))
        self.ui.label_2.setText(
            self.api.tr(
                "ui.label_details",
                (
                    "<html><head/><body><p>This option determines whether or not County, Municipality and Subdivision information is "
                    "included in the artist location variables created. Regardless of these settings, this information will be included "
                    "if a County, Municipality or Subdivision is the area specified for an artist.</p></body></html>"
                )
            )
        )
        self.ui.cb_area_county.setText(self.api.tr("ui.cb_area_county", "Include location county"))
        self.ui.cb_area_municipality.setText(self.api.tr("ui.cb_area_municipality", "Include location municipality"))
        self.ui.cb_area_subdivision.setText(self.api.tr("ui.cb_area_subdivision", "Include location subdivision"))

        # Enable external link
        self.ui.format_description.setOpenExternalLinks(True)

    def load(self):
        """Load the option settings.
        """
        self.ui.cb_process_tracks.setChecked(self.api.plugin_config[OPT_PROCESS_TRACKS])
        self.ui.cb_area_county.setChecked(self.api.plugin_config[OPT_AREA_COUNTY])
        self.ui.cb_area_municipality.setChecked(self.api.plugin_config[OPT_AREA_MUNICIPALITY])
        self.ui.cb_area_subdivision.setChecked(self.api.plugin_config[OPT_AREA_SUBDIVISION])

    def save(self):
        """Save the option settings.
        """
        self.api.plugin_config[OPT_PROCESS_TRACKS] = self.ui.cb_process_tracks.isChecked()
        self.api.plugin_config[OPT_AREA_COUNTY] = self.ui.cb_area_county.isChecked()
        self.api.plugin_config[OPT_AREA_MUNICIPALITY] = self.ui.cb_area_municipality.isChecked()
        self.api.plugin_config[OPT_AREA_SUBDIVISION] = self.ui.cb_area_subdivision.isChecked()


def enable(api: PluginApi):
    """Called when plugin is enabled."""
    api.plugin_config.register_option(OPT_PROCESS_TRACKS, False)
    api.plugin_config.register_option(OPT_AREA_COUNTY, True)
    api.plugin_config.register_option(OPT_AREA_MUNICIPALITY, True)
    api.plugin_config.register_option(OPT_AREA_SUBDIVISION, True)

    plugin = ArtistDetailsPlugin(api)
    api.register_options_page(AdditionalArtistsDetailsOptionsPage)
    api.register_album_post_removal_processor(plugin.remove_album)

    # Register the plugin to run at a high priority.
    api.register_album_metadata_processor(plugin.make_album_vars, priority=100)
    api.register_track_metadata_processor(plugin.make_track_vars, priority=100)
