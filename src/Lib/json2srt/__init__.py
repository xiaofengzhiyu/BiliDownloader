import collections

_timetuple = collections.namedtuple('Time', ('hours', 'minutes', 'seconds', 'milliseconds'))


def format_time(milliseconds):
    """将毫秒转换为 SRT 时间格式 (HH:MM:SS,mmm)"""
    hours = milliseconds // (3600 * 1000)
    milliseconds %= (3600 * 1000)
    minutes = milliseconds // (60 * 1000)
    milliseconds %= (60 * 1000)
    seconds = milliseconds // 1000
    milliseconds %= 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def timetuple_from_msec(msec):
    secs, msec = divmod(msec, 1000)
    mins, secs = divmod(secs, 60)
    hrs, mins = divmod(mins, 60)
    return _timetuple(hrs, mins, secs, msec)


def srt_subtitles_timecode(seconds):
    return '%02d:%02d:%02d,%03d' % timetuple_from_msec(seconds * 1000)


def json2srt(json_data):
    srt_data = ''
    for idx, line in enumerate(json_data['body'] or []):
        srt_data += (f'{idx + 1}\n'
                     f'{srt_subtitles_timecode(line["from"])} --> {srt_subtitles_timecode(line["to"])}\n'
                     f'{line["content"]}\n\n')
    return srt_data
