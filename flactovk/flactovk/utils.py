#!/usr/bin/python

#Audio Tools, a module and set of tools for manipulating audio data
#Copyright (C) 2007-2013  Brian Langenberger

#This program is free software; you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation; either version 2 of the License, or
#(at your option) any later version.

#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with this program; if not, write to the Free Software
#Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA


import sys
import os
import os.path
import select
import cPickle
from operator import concat
from itertools import izip
import audiotools
import audiotools.ui
import audiotools.text as _
import termios


MAX_CPUS = audiotools.MAX_JOBS


def convert(progress, source_audiofile, destination_filename,
            destination_class, compression, metadata,
            sample_rate, channels, bits_per_sample):
    if (((sample_rate is None) and
             (channels is None) and
             (bits_per_sample is None))):
        destination_audiofile = source_audiofile.convert(
            destination_filename,
            destination_class,
            compression,
            progress)
    else:
        pcmreader = source_audiofile.to_pcm()
        destination_audiofile = destination_class.from_pcm(
            destination_filename,
            audiotools.PCMConverter(
                audiotools.PCMReaderProgress(
                    pcmreader,
                    source_audiofile.total_frames(),
                    progress),
                sample_rate if
                (sample_rate is not None) else
                pcmreader.sample_rate,
                channels if
                (channels is not None) else
                pcmreader.channels,
                0 if
                (channels is not None) else
                pcmreader.channel_mask,
                bits_per_sample if (bits_per_sample is not None) else
                pcmreader.bits_per_sample),
            compression,
            source_audiofile.total_frames() if
            (source_audiofile.lossless() and (sample_rate is None))
            else None)

    if (metadata is not None):
        destination_audiofile.set_metadata(metadata)

    existing_cuesheet = source_audiofile.get_cuesheet()
    if (existing_cuesheet is not None):
        destination_audiofile.set_cuesheet(existing_cuesheet)

    return destination_filename


if (audiotools.ui.AVAILABLE):
    urwid = audiotools.ui.urwid

    class MultiOutputFiller(audiotools.ui.OutputFiller):
        def __init__(self,
                     track_labels,
                     metadata_choices,
                     input_filenames,
                     output_directory,
                     format_string,
                     output_class,
                     quality,
                     completion_label=u"Apply"):
            """track_labels[a][t]
            is a unicode string per album "a", per track "t"

            metadata_choices[a][c][t]
            is a MetaData object per album "a", per choice "c", per track "t"
            must have same album count as track_labels
            and each album's choice must have the same number of tracks
            (but may have different number of choices)

            input_filenames[a][t]
            is a Filename object per album "a", per track "t"

            output_directory is a string of the default output dir

            format_string is a UTF-8 encoded format string

            output_class is the default AudioFile-compatible class

            quality is a string of the default output quality to use
            """

            self.__cancelled__ = True

            #ensure there's at least one album
            assert(len(track_labels) > 0)

            #ensure album count is consistent
            assert(len(track_labels) ==
                   len(metadata_choices) ==
                   len(input_filenames))

            #ensure track count is consistent
            for (labels, filenames) in zip(track_labels, input_filenames):
                assert(len(labels) == len(filenames))

            #ensure there's at least one track
            assert(len(track_labels[0]) > 0)

            #ensure there's at least one set of choices per album
            #and all have the same number of tracks
            for (a, choice_labels) in zip(metadata_choices,
                                          track_labels):
                assert(len(a) > 0)
                for c in a:
                    assert(len(c) == len(choice_labels))

            #ensure all input filenames are Filename objects
            for a in input_filenames:
                for f in a:
                    assert(isinstance(f, audiotools.Filename))

            #setup status bars for output messages
            self.metadatas_status = [urwid.Text(u"") for m in track_labels]
            self.options_status = urwid.Text(u"")

            #setup widgets for populated metadata fields
            self.metadatas = [
                audiotools.ui.MetaDataFiller(labels, choices, status)
                for (labels, choices, status) in zip(track_labels,
                                                     metadata_choices,
                                                     self.metadatas_status)]

            #setup a widget for populating output parameters
            self.options = audiotools.ui.OutputOptions(
                output_dir=output_directory,
                format_string=format_string,
                audio_class=output_class,
                quality=quality,
                input_filenames=reduce(concat, input_filenames),
                metadatas=[None for f in reduce(concat, input_filenames)])

            #finish initialization
            from audiotools.text import LAB_CANCEL_BUTTON

            self.wizard = audiotools.ui.Wizard(
                self.metadatas + [self.options],
                urwid.Button(LAB_CANCEL_BUTTON, on_press=self.exit),
                urwid.Button(completion_label, on_press=self.complete),
                self.page_changed)

            self.__current_page__ = self.metadatas[0]

            urwid.Frame.__init__(self,
                                 body=self.wizard,
                                 footer=self.metadatas_status[0])

        def page_changed(self, new_page):
            self.__current_page__ = new_page
            if (hasattr(new_page, "status")):
                #one of the metadata pages is selected
                self.set_footer(new_page.status)
            else:
                #the final options page is selected
                self.options.set_metadatas(
                    reduce(concat, [list(m.populated_metadata())
                                    for m in self.metadatas]))
                self.set_footer(self.options_status)

        def handle_text(self, i):
            if ((i == "f1") and hasattr(self.__current_page__,
                                        "select_previous_item")):
                self.__current_page__.select_previous_item()
            elif ((i == "f2") and (hasattr(self.__current_page__,
                                           "select_next_item"))):
                self.__current_page__.select_next_item()

        def output_tracks(self):
            """yields (output_class,
                       output_filename,
                       output_quality,
                       output_metadata) tuple for each input audio file

            output_metadata is a newly created MetaData object"""

            from itertools import izip

            (audiofile_class,
             quality,
             output_filenames) = self.options.selected_options()

            output_filenames = iter(output_filenames)

            for widget in self.metadatas:
                for (metadata,
                     output_filename) in izip(widget.populated_metadata(),
                                              output_filenames):
                    yield (audiofile_class,
                           output_filename,
                           quality,
                           metadata)


if (__name__ == '__main__'):
    parser = audiotools.OptionParser(
        usage=_.USAGE_TRACK2TRACK,
        version="Python Audio Tools %s" % (audiotools.VERSION))

    parser.add_option(
        '-I', '--interactive',
        action='store_true',
        default=False,
        dest='interactive',
        help=_.OPT_INTERACTIVE_OPTIONS)

    parser.add_option(
        '-V', '--verbose',
        action='store',
        dest='verbosity',
        choices=audiotools.VERBOSITY_LEVELS,
        default=audiotools.DEFAULT_VERBOSITY,
        help=_.OPT_VERBOSE)

    conversion = audiotools.OptionGroup(parser, _.OPT_CAT_CONVERSION)

    conversion.add_option(
        '-t', '--type',
        action='store',
        dest='type',
        choices=sorted(audiotools.TYPE_MAP.keys() + ['help']),
        help=_.OPT_TYPE)

    conversion.add_option(
        '-q', '--quality',
        action='store',
        type='string',
        dest='quality',
        help=_.OPT_QUALITY)

    conversion.add_option(
        '-d', '--dir',
        action='store',
        type='string',
        dest='dir',
        default='.',
        help=_.OPT_DIR)

    conversion.add_option(
        '--format',
        action='store',
        type='string',
        default=None,
        dest='format',
        help=_.OPT_FORMAT)

    conversion.add_option(
        '-o', '--output',
        action='store',
        dest='output',
        help=_.OPT_OUTPUT_TRACK2TRACK)

    conversion.add_option(
        '-j', '--joint',
        action='store',
        type='int',
        default=MAX_CPUS,
        dest='max_processes',
        help=_.OPT_JOINT)

    parser.add_option_group(conversion)

    format = audiotools.OptionGroup(parser, _.OPT_CAT_OUTPUT_FORMAT)

    format.add_option(
        '--sample-rate',
        action='store',
        type='int',
        dest='sample_rate',
        metavar="RATE",
        help=_.OPT_SAMPLE_RATE)

    format.add_option(
        '--channels',
        action='store',
        type='int',
        dest='channels',
        help=_.OPT_CHANNELS)

    format.add_option(
        '--bits-per-sample',
        action='store',
        type='int',
        dest='bits_per_sample',
        metavar="BITS",
        help=_.OPT_BPS)

    parser.add_option_group(format)

    lookup = audiotools.OptionGroup(parser, _.OPT_CAT_CD_LOOKUP)

    lookup.add_option(
        '-M', '--metadata-lookup', action='store_true',
        default=False, dest='metadata_lookup',
        help=_.OPT_METADATA_LOOKUP)

    lookup.add_option(
        '--musicbrainz-server', action='store',
        type='string', dest='musicbrainz_server',
        default=audiotools.MUSICBRAINZ_SERVER,
        metavar='HOSTNAME')
    lookup.add_option(
        '--musicbrainz-port', action='store',
        type='int', dest='musicbrainz_port',
        default=audiotools.MUSICBRAINZ_PORT,
        metavar='PORT')
    lookup.add_option(
        '--no-musicbrainz', action='store_false',
        dest='use_musicbrainz',
        default=audiotools.MUSICBRAINZ_SERVICE,
        help=_.OPT_NO_MUSICBRAINZ)

    lookup.add_option(
        '--freedb-server', action='store',
        type='string', dest='freedb_server',
        default=audiotools.FREEDB_SERVER,
        metavar='HOSTNAME')
    lookup.add_option(
        '--freedb-port', action='store',
        type='int', dest='freedb_port',
        default=audiotools.FREEDB_PORT,
        metavar='PORT')
    lookup.add_option(
        '--no-freedb', action='store_false',
        dest='use_freedb',
        default=audiotools.FREEDB_SERVICE,
        help=_.OPT_NO_FREEDB)

    lookup.add_option(
        '-D', '--default',
        dest='use_default', action='store_true', default=False,
        help=_.OPT_DEFAULT)

    parser.add_option_group(lookup)

    metadata = audiotools.OptionGroup(parser, _.OPT_CAT_METADATA)

    metadata.add_option(
        '--replay-gain',
        action='store_true',
        dest='add_replay_gain',
        help=_.OPT_REPLAY_GAIN)

    metadata.add_option(
        '--no-replay-gain',
        action='store_false',
        dest='add_replay_gain',
        help=_.OPT_NO_REPLAY_GAIN)

    parser.add_option_group(metadata)

    (options, args) = parser.parse_args()
    msg = audiotools.Messenger("track2track", options)

    #ensure interactive mode is available, if selected
    if (options.interactive and (not audiotools.ui.AVAILABLE)):
        audiotools.ui.not_available_message(msg)
        sys.exit(1)

    #if one specifies incompatible output options,
    #complain about it right away
    if (options.output is not None):
        if (options.dir != "."):
            msg.error(_.ERR_TRACK2TRACK_O_AND_D)
            msg.info(_.ERR_TRACK2TRACK_O_AND_D_SUGGESTION)
            sys.exit(1)

        if (options.format is not None):
            msg.warning(_.ERR_TRACK2TRACK_O_AND_FORMAT)

    #get the AudioFile class we are converted to
    if (options.type == 'help'):
        audiotools.ui.show_available_formats(msg)
        sys.exit(0)
    elif (options.output is None):
        if (options.type is not None):
            AudioType = audiotools.TYPE_MAP[options.type]
        else:
            AudioType = audiotools.TYPE_MAP[audiotools.DEFAULT_TYPE]
    else:
        if (options.type is not None):
            AudioType = audiotools.TYPE_MAP[options.type]
        else:
            try:
                AudioType = audiotools.filename_to_type(options.output)
            except audiotools.UnknownAudioType, exp:
                exp.error_msg(msg)
                sys.exit(1)

    #ensure the selected compression is compatible with that class
    if (options.quality == 'help'):
        audiotools.ui.show_available_qualities(msg, AudioType)
        sys.exit(0)
    elif (options.quality is None):
        options.quality = audiotools.__default_quality__(AudioType.NAME)
    elif (options.quality not in AudioType.COMPRESSION_MODES):
        msg.error(_.ERR_UNSUPPORTED_COMPRESSION_MODE %
                  {"quality": options.quality,
                   "type": AudioType.NAME})
        sys.exit(1)

    #grab the list of AudioFile objects we are converting from
    input_filenames = set([])
    try:
        audiofiles = audiotools.open_files(args,
                                           messenger=msg,
                                           no_duplicates=True,
                                           opened_files=input_filenames)
    except audiotools.DuplicateFile, err:
        msg.error(_.ERR_DUPLICATE_FILE % (err.filename,))
        sys.exit(1)

    if (len(audiofiles) < 1):
        msg.error(_.ERR_FILES_REQUIRED)
        sys.exit(1)

    if ((options.sample_rate is not None) and
            (options.sample_rate < 1)):
        msg.error(_.ERR_INVALID_SAMPLE_RATE)
        sys.exit(1)

    if ((options.channels is not None) and
            (options.channels < 1)):
        msg.error(_.ERR_INVALID_CHANNEL_COUNT)
        sys.exit(1)

    if ((options.bits_per_sample is not None) and
            (options.bits_per_sample < 1)):
        msg.error(_.ERR_INVALID_BITS_PER_SAMPLE)
        sys.exit(1)

    if (options.max_processes < 1):
        msg.error(_.ERR_INVALID_JOINT)
        sys.exit(1)

    if ((options.output is not None) and (len(audiofiles) != 1)):
        msg.error(_.ERR_TRACK2TRACK_O_AND_MULTIPLE)
        sys.exit(1)

    if (options.output is None):
        #the default encoding method, without an output file

        previous_output_widget = None
        queue = audiotools.ExecProgressQueue(audiotools.ProgressDisplay(msg))

        #split tracks by album only if metadata lookups are required
        if (options.metadata_lookup):
            albums_iter = audiotools.group_tracks(audiofiles)
        else:
            albums_iter = iter([audiofiles])

        filename_format = (audiotools.FILENAME_FORMAT if
                           options.format is None else
                           options.format)

        #input_tracks[a][t] is an AudioFile object
        #per album "a", per track "t"
        input_tracks = []

        #input_metadatas[a][t] is a MetaData object (or None)
        #per album "a", per track "t"
        input_metadatas = []

        #track_labels[a][t] is a unicode string per album "a", per track "t"
        track_labels = []

        #metadata_choices[a][c][t] is a MetaData object
        #per album "a", per choice "c", per track "t"
        metadata_choices = []

        #input_filenames[a][t] is a Filename object
        #per album "a", per track "t"
        input_filenames = []

        for album_tracks in albums_iter:
            input_tracks.append(album_tracks)

            track_metadatas = [f.get_metadata() for f in album_tracks]
            input_metadatas.append(track_metadatas)

            filenames = [audiotools.Filename(f.filename) for f in album_tracks]
            track_labels.append([unicode(f.basename()) for f in filenames])
            input_filenames.append(filenames)

            if (not options.metadata_lookup):
                #pull metadata from existing files, if any
                metadata_choices.append([[f.get_metadata() for f in
                                          album_tracks]])
            else:
                #perform CD lookup for existing files
                metadata_choices.append(audiotools.track_metadata_lookup(
                    audiofiles=album_tracks,
                    musicbrainz_server=options.musicbrainz_server,
                    musicbrainz_port=options.musicbrainz_port,
                    freedb_server=options.freedb_server,
                    freedb_port=options.freedb_port,
                    use_musicbrainz=options.use_musicbrainz,
                    use_freedb=options.use_freedb))

                #and prepend metadata from existing files as an option, if any
                if (track_metadatas != [None] * len(track_metadatas)):
                    metadata_choices[-1].insert(
                        0,
                        [(m if m is not None else audiotools.MetaData())
                         for m in track_metadatas])

                #avoid performing too many lookups in a row too quickly
                from time import sleep
                sleep(1)

        #a list of (audiofile,
        #           output_class,
        #           output_filename,
        #           output_quality,
        #           output_metadata) tuples to be executed
        conversion_jobs = []

        if (options.interactive):
            #pick options using interactive widget

            output_widget = MultiOutputFiller(
                track_labels=track_labels,
                metadata_choices=metadata_choices,
                input_filenames=input_filenames,
                output_directory=options.dir,
                format_string=filename_format,
                output_class=AudioType,
                quality=options.quality,
                completion_label=(_.LAB_TRACK2TRACK_APPLY if
                                  (sum(map(len, input_tracks)) != 1)
                                  else _.LAB_TRACK2TRACK_APPLY_1))

            loop = audiotools.ui.urwid.MainLoop(
                output_widget,
                audiotools.ui.style(),
                unhandled_input=output_widget.handle_text,
                pop_ups=True)
            try:
                loop.run()
                msg.ansi_clearscreen()
            except (termios.error, IOError):
                msg.error(_.ERR_TERMIOS_ERROR)
                msg.info(_.ERR_TERMIOS_SUGGESTION)
                msg.info(audiotools.ui.xargs_suggestion(sys.argv))
                sys.exit(1)

            if (output_widget.cancelled()):
                sys.exit(0)

            for (input_track,
                 current_metadata,
                 (output_class,
                  output_filename,
                  output_quality,
                  output_metadata)) in izip(iter(reduce(concat,
                                                        input_tracks)),
                                            iter(reduce(concat,
                                                        input_metadatas)),
                                            output_widget.output_tracks()):
                #merge current track metadata (if any)
                #with metadata returned from widget
                if (current_metadata is not None):
                    for attr in audiotools.MetaData.FIELDS:
                        original_value = getattr(current_metadata, attr)
                        updated_value = getattr(output_metadata, attr)
                        if (original_value != updated_value):
                            setattr(current_metadata, attr, updated_value)
                        #and queue up conversion job to be executed
                    conversion_jobs.append((input_track,
                                            output_class,
                                            output_filename,
                                            output_quality,
                                            current_metadata))
                else:
                    #or simply queue up conversion job to be executed
                    #using only new metadata
                    conversion_jobs.append((input_track,
                                            output_class,
                                            output_filename,
                                            output_quality,
                                            output_metadata))

        else:
            #pick options without using GUI
            for (album_tracks,
                 album_metadata_choices,
                 album_filenames) in zip(input_tracks,
                                         metadata_choices,
                                         input_filenames):
                try:
                    output_tracks = audiotools.ui.process_output_options(
                        metadata_choices=album_metadata_choices,
                        input_filenames=album_filenames,
                        output_directory=options.dir,
                        format_string=filename_format,
                        output_class=AudioType,
                        quality=options.quality,
                        msg=msg,
                        use_default=options.use_default)

                    #queue jobs to be executed
                    for (album_track,
                         (output_class,
                          output_filename,
                          output_quality,
                          output_metadata)) in izip(album_tracks,
                                                    output_tracks):
                        conversion_jobs.append((album_track,
                                                output_class,
                                                output_filename,
                                                output_quality,
                                                output_metadata))
                except audiotools.UnsupportedTracknameField, err:
                    err.error_msg(msg)
                    sys.exit(1)
                except (audiotools.InvalidFilenameFormat,
                        audiotools.OutputFileIsInput,
                        audiotools.DuplicateOutputFile), err:
                    msg.error(unicode(err))
                    sys.exit(1)

        #queue conversion jobs to ProgressQueue
        for (audiofile,
             output_class,
             output_filename,
             output_quality,
             output_metadata) in conversion_jobs:
            #try to create subdirectories in advance
            #so to bail out early if there's an error creating one
            try:
                audiotools.make_dirs(str(output_filename))
            except OSError:
                msg.error(_.ERR_ENCODING_ERROR % (output_filename,))
                sys.exit(1)

            queue.execute(
                function=convert,
                progress_text=unicode(output_filename),
                completion_output=
                (_.LAB_ENCODE %
                 {"source": audiotools.Filename(audiofile.filename),
                  "destination": output_filename}),
                source_audiofile=audiofile,
                destination_filename=str(output_filename),
                destination_class=output_class,
                compression=output_quality,
                metadata=output_metadata,
                sample_rate=options.sample_rate,
                channels=options.channels,
                bits_per_sample=options.bits_per_sample)

        #perform actual track conversion
        try:
            output_files = audiotools.open_files(
                queue.run(options.max_processes))
        except audiotools.EncodingError, err:
            msg.error(unicode(err))
            sys.exit(1)

        #add ReplayGain to converted files, if necessary
        if ((audiotools.ADD_REPLAYGAIN and
                 (options.add_replay_gain if (options.add_replay_gain is not None)
                  else output_class.lossless_replay_gain()) and
                 output_class.can_add_replay_gain(output_files))):
            #separate encoded files by album_name and album_number
            for album in audiotools.group_tracks(output_files):
                #add ReplayGain to groups of files
                #belonging to the same album

                album_number = set([(m.album_number if m is not None else None)
                                    for m in
                                    [f.get_metadata() for f in album]]).pop()

                #FIXME - should pull ReplayGain text from elsewhere
                queue.execute(
                    output_class.add_replay_gain,
                    (u"%s ReplayGain%s" %
                     ((u"Adding" if output_class.lossless_replay_gain() else
                       u"Applying"),
                      (u"" if album_number is None else
                       (u" to album %d" % (album_number))))),
                    (u"ReplayGain %s%s" %
                     ((u"added" if output_class.lossless_replay_gain() else
                       u"applied"),
                      (u"" if album_number is None else
                       (u" to album %d" % (album_number))))),
                    [a.filename for a in album])

            try:
                queue.run(options.max_processes)
            except ValueError, err:
                msg.error(unicode(err))
                sys.exit(1)
    else:
        #encoding only a single file
        audiofile = audiofiles[0]
        input_filename = audiotools.Filename(audiofile.filename)

        if (options.interactive):
            track_metadata = audiofile.get_metadata()

            output_widget = audiotools.ui.SingleOutputFiller(
                track_label=unicode(input_filename),
                metadata_choices=[track_metadata if track_metadata is not None
                                  else audiotools.MetaData()],
                input_filenames=[input_filename],
                output_file=options.output,
                output_class=AudioType,
                quality=options.quality,
                completion_label=_.LAB_TRACK2TRACK_APPLY_1)
            loop = audiotools.ui.urwid.MainLoop(
                output_widget,
                audiotools.ui.style(),
                unhandled_input=output_widget.handle_text,
                pop_ups=True)
            loop.run()
            msg.ansi_clearscreen()

            if (not output_widget.cancelled()):
                (destination_class,
                 output_filename,
                 compression,
                 track_metadata) = output_widget.output_track()
            else:
                sys.exit(0)
        else:
            output_filename = audiotools.Filename(options.output)
            destination_class = AudioType
            compression = options.quality
            track_metadata = audiofile.get_metadata()

            if (input_filename == output_filename):
                msg.error(_.ERR_OUTPUT_IS_INPUT %
                          (output_filename,))
                sys.exit(1)

        progress = audiotools.SingleProgressDisplay(
            messenger=msg,
            progress_text=unicode(output_filename))
        try:
            convert(progress=progress.update,
                    source_audiofile=audiofile,
                    destination_filename=str(output_filename),
                    destination_class=destination_class,
                    compression=compression,
                    metadata=track_metadata,
                    sample_rate=options.sample_rate,
                    channels=options.channels,
                    bits_per_sample=options.bits_per_sample)
            progress.clear()

            msg.output(_.LAB_ENCODE % {"source": input_filename,
                                       "destination": output_filename})
        except audiotools.EncodingError, err:
            progress.clear()
            msg.error(unicode(err))
            sys.exit(1)