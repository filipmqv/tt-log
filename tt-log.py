#!/usr/bin/python
import json
from argparse import ArgumentParser
from datetime import date, datetime, timedelta
from typing import List

import attr
import pytz
import requests
from dateutil import parser

# config consts
CONFIG_FILE = 'tt-log-config.json'
JIRA = 'jira'
ASSIGNEE_NAME = 'assignee_name'
USERNAME = 'username'
PASSWORD = 'password'
PROJECT_ABBR = 'project_abbr'
STATUS_FIELD = 'status_field'
TEAMTRACKER = 'teamtracker'
TT_PROJECT_ID = 'tt_project_id'
WORK_HOURS = 8

# jira
CHANGELOG = 'changelog'
HISTORIES = 'histories'
FIELDS = 'fields'
ASSIGNEE = 'assignee'
ITEMS = 'items'
FIELD = 'field'
KEY = 'key'
WORK_TIME = 'work_time'
TO_STRING = 'toString'
CREATED = 'created'
SUMMARY = 'summary'

MEETINGS = 'meetings'
DAILY_EVENTS = 'daily_events'
WEEKLY_EVENTS = 'weekly_events'
BIWEEKLY_EVENTS = 'biweekly_events'


class TeamTrackerLoggerError(Exception):
    pass


def make_parser():
    arg_parser = ArgumentParser('Log work time to TeamTracker')

    arg_parser.add_argument('-w', '--when', dest='date_to_compare', type=str,
                            help='Provide date for which you want to log work')
    arg_parser.add_argument('-m', '--meeting', dest='additional_meeting',
                            type=str,
                            help='Add additional meeting to your regular meetings. Format: "description:minutes"')
    arg_parser.add_argument('-o', '--override-meeting', dest='override_meeting',
                            type=str,
                            help='Disregard regular meetings and override them with provided meeting. Format: "description:minutes"')
    arg_parser.add_argument('-y', '--yolo', dest='yolo', action='store_true',
                            help='Log to TT immediately. YOLO')

    return arg_parser


def validate_args(args):
    def _get_event(args_string: str):
        try:
            title, work_time = args_string.split(":")
            return Event(
                title=title,
                work_time=timedelta(minutes=int(work_time))
            )
        except:
            raise TeamTrackerLoggerError(f'Could not parse {args_string}')

    if args.date_to_compare:
        try:
            parser.parse(args.date_to_compare)
        except:
            raise TeamTrackerLoggerError('Could not parse date to compare')
    if args.additional_meeting:
        args.additional_meeting = _get_event(args.additional_meeting)
    if args.override_meeting:
        args.override_meeting = _get_event(args.override_meeting)


def parse_args(args=None):
    parsed_args = make_parser().parse_args(args)
    validate_args(parsed_args)
    return parsed_args


@attr.dataclass
class JiraConfig:
    username: str
    password: str
    assignee_name: str
    project_abbr: str
    status_field: str
    start_work_status: str
    stop_work_status_primary: str
    stop_work_status_secondary: str


class EventType:
    OTHER = 1
    TASK = 2
    MEETING = 3


@attr.dataclass(repr=False)
class Event:
    work_time: timedelta
    key: str = ''
    title: str = ''
    event_type: int = EventType.OTHER

    def __repr__(self):
        return '{} - {}'.format(self.work_time, self.description)

    @property
    def minutes(self):
        return int(self.work_time.total_seconds() / 60)

    @property
    def description(self):
        return " ".join(filter(None, [self.key, self.title]))


@attr.dataclass
class ConfigLoader:
    _config_file: str

    def process_config(self):
        config = self.get_config_from_file()
        config['timezone'] = pytz.timezone(config['timezone'])
        if config[MEETINGS]['biweekly_start_date']:
            config[MEETINGS]['biweekly_start_date'] = parser.parse(
                config[MEETINGS]['biweekly_start_date']).date()
        return config

    def get_config_from_file(self):
        with open(self._config_file, 'r') as f:
            config = json.load(f)
        return config


@attr.dataclass
class MeetingsBuilder:
    _date_to_compare: date

    def get_meetings(self, meetings_dict) -> List[Event]:
        sprint = meetings_dict['sprint']

        meetings = self._build_event_list(meetings_dict[DAILY_EVENTS])
        if sprint == 'weekly':
            weekly = self._build_event_list(meetings_dict[WEEKLY_EVENTS])
            meetings.append(weekly[self._date_to_compare.weekday()])
            return meetings
        elif sprint == 'biweekly':
            week_modifier = self._week_modifier(
                meetings_dict['biweekly_start_date'])
            biweekly = self._build_event_list(meetings_dict[BIWEEKLY_EVENTS])
            meetings.append(
                biweekly[self._date_to_compare.weekday() + week_modifier])
            return meetings
        else:
            raise TeamTrackerLoggerError(f'Unexpected type of sprint: {sprint}')

    def _build_event_list(self, meeting_list):
        return [Event(
            title=e['title'],
            work_time=timedelta(minutes=e[WORK_TIME]),
            event_type=EventType.MEETING
        ) for e in meeting_list]

    def _week_modifier(self, biweekly_start_date):
        biweekly_start_date = biweekly_start_date
        if biweekly_start_date > self._date_to_compare:
            raise TeamTrackerLoggerError(
                'Fix biweekly_start_date - it should be less than date you want to log')
        while biweekly_start_date < self._date_to_compare:
            new_biweekly_start_date = biweekly_start_date + timedelta(days=14)
            if new_biweekly_start_date < self._date_to_compare:
                biweekly_start_date = new_biweekly_start_date
            else:
                break

        return 0 if self._is_first_week(biweekly_start_date) else 5

    def _is_first_week(self, biweekly_start_date):
        return self._date_to_compare - biweekly_start_date < timedelta(days=7)


class TaskGetter:
    def get_tasks(self):
        raise NotImplementedError


class FileTaskGetter(TaskGetter):
    def get_tasks(self):
        with open('results-full.json') as json_file:
            data = json.load(json_file)
        return data


@attr.dataclass
class JiraTaskGetter(TaskGetter):
    _config: JiraConfig

    JIRA_URL = 'https://venturedevs.atlassian.net'
    SEARCH_ENDPOINT = JIRA_URL + '/rest/api/3/search'

    def get_tasks(self):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        payload = json.dumps({
            "expand": [
                "changelog"
            ],
            "jql": "project = {} AND assignee = {}".format(
                self._config.project_abbr, self._config.assignee_name),
            "maxResults": 100,
            "fields": [
                "summary",
                "status",
                "assignee"
            ],
            "startAt": 0
        })

        r = requests.request(
            "POST",
            self.SEARCH_ENDPOINT,
            data=payload,
            headers=headers,
            auth=(self._config.username, self._config.password)
        )
        data = r.json()

        # with open('results4.json', 'w') as file:
        #     file.write(json.dumps(data))
        #     print('done')

        return data


@attr.dataclass
class JiraTaskProcessor:
    _config: JiraConfig
    _date_to_compare: date
    _start_work_timestamp: datetime
    _stop_work_timestamp: datetime

    def process_jira_tasks(self, data):
        data = self._get_issues_for_assigne(data, self._config.assignee_name)
        data = [self._convert_to_event(obj, self._date_to_compare)
                for obj in data if
                obj[CHANGELOG] and
                obj[CHANGELOG][HISTORIES] and
                self._is_updated_on_date(obj[CHANGELOG][HISTORIES], obj[KEY])]

        data = [event for event in data if event.work_time]
        return data

    def _convert_to_event(self, issue, date_to_compare):
        histories = issue[CHANGELOG][HISTORIES]
        key = issue[KEY]
        title = issue[FIELDS][SUMMARY]

        histories_to_primary_stop = self._histories_moved_to_status(
            histories, self._config.stop_work_status_primary)
        histories_to_secondary_stop = self._histories_moved_to_status(
            histories, self._config.stop_work_status_secondary)
        histories_to_start = self._histories_moved_to_status(
            histories, self._config.start_work_status)
        
        newest_start_work = self._get_newest_created_datetime(
            histories_to_start)
        newest_stop_work = self._get_newest_created_datetime(
            histories_to_primary_stop) or \
                           self._get_newest_created_datetime(
                               histories_to_secondary_stop)

        work_time = None
        if newest_start_work and \
                newest_stop_work and \
                newest_start_work.date() == date_to_compare and \
                newest_stop_work.date() == date_to_compare:
            work_time = newest_stop_work - newest_start_work
        elif newest_start_work and newest_start_work.date() == date_to_compare:
            work_time = self._stop_work_timestamp - newest_start_work
        elif newest_stop_work and newest_stop_work.date() == date_to_compare:
            work_time = newest_stop_work - self._start_work_timestamp
        else:
            print('Discarded: {} {} {}'.format(key, newest_start_work,
                                               newest_stop_work))
        return Event(work_time=work_time, key=key, title=title,
                     event_type=EventType.TASK)

    def _histories_moved_to_status(self, histories, status):
        histories = [obj for obj in histories if
                     obj[ITEMS] and
                     obj[ITEMS][0] and
                     obj[ITEMS][0][FIELD] == self._config.status_field and
                     obj[ITEMS][0][TO_STRING] == status]
        return histories

    @staticmethod
    def _get_newest_created_datetime(histories):
        if histories and histories[0] and histories[0][CREATED]:
            return parser.parse(histories[0][CREATED])
        return None

    def _is_on_date(self, created_timestamp):
        return parser.parse(created_timestamp).date() == self._date_to_compare

    def _is_updated_on_date(self, histories, key):
        histories_to_primary_stop = self._histories_moved_to_status(
            histories, self._config.stop_work_status_primary)
        histories_to_secondary_stop = self._histories_moved_to_status(
            histories, self._config.stop_work_status_secondary)
        histories_to_start = self._histories_moved_to_status(
            histories, self._config.start_work_status)

        histories = [obj for obj in histories_to_secondary_stop if
                     self._is_on_date(obj[CREATED])] or \
                    [obj for obj in histories_to_primary_stop if
                     self._is_on_date(obj[CREATED])] or \
                    [obj for obj in histories_to_start if
                     self._is_on_date(obj[CREATED])]
        return bool(histories)

    def _get_issues_for_assigne(self, data, assignee):
        return [obj for obj in data['issues'] if
                obj[FIELDS] and
                obj[FIELDS][ASSIGNEE] and
                obj[FIELDS][ASSIGNEE]['name'] == assignee]


class TimeAdjuster:
    def adjust_time(self, tasks: List[Event], meetings: List[Event]):
        workday_hours = timedelta(hours=WORK_HOURS)
        all_events_time = sum([obj.work_time for obj in meetings], timedelta())
        all_tasks_time = sum([obj.work_time for obj in tasks], timedelta())
        if all_tasks_time == timedelta(seconds=0):
            raise TeamTrackerLoggerError('No tasks to log')
        tasks_must_be_time = workday_hours - all_events_time
        tasks_times = [obj.work_time for obj in tasks]
        proportions = self._proportions(tasks_times)
        results = [(tasks_must_be_time * p) for p in proportions]
        results2 = [self._round_timedelta(r) for r in results]
        diff_after_rounding = tasks_must_be_time - sum(results2, timedelta())
        if diff_after_rounding > timedelta(seconds=0):
            time_idx = results2.index(min(results2))
        else:
            time_idx = results2.index(max(results2))
        results2[time_idx] += diff_after_rounding
        new_all_tasks_time = sum([obj for obj in results], timedelta())
        for task, new_work_time in zip(tasks, results2):
            task.work_time = new_work_time
        return tasks

    @staticmethod
    def _round_timedelta(td, period=timedelta(minutes=5)):
        """
        Rounds the given timedelta by the given timedelta period
        :param td: `timedelta` to round
        :param period: `timedelta` period to round by.
        """
        period_seconds = period.total_seconds()
        half_period_seconds = period_seconds / 2
        remainder = td.total_seconds() % period_seconds
        if remainder >= half_period_seconds:
            return timedelta(
                seconds=td.total_seconds() + (period_seconds - remainder),
                microseconds=0
            )
        else:
            return timedelta(
                seconds=td.total_seconds() - remainder,
                microseconds=0
            )

    @staticmethod
    def _proportions(items: List) -> List[float]:
        """
        Returns proportions of given items
        """
        sum_of_items = sum(items, timedelta())
        if sum_of_items == 0:
            return [0 for i in items]
        else:
            percentages = [(i / sum_of_items) for i in items]
            return percentages


@attr.dataclass
class TeamTrackerLogger:
    _tt_project_id: int
    _auth: str
    _when: date

    TT_URL = 'http://localhost:8080'
    LOG_ENDPOINT = TT_URL + '/api/project_logs/'
    
    def post_log(self, events: List[Event]):
        for event in events:
            if event.work_time > timedelta(seconds=0):
                payload = self._prepare_payload(
                    event.description,
                    event.minutes,
                    event.event_type
                )
                self._post_payload(payload)

    def _prepare_payload(self, description, minutes, event_type):
        payload = json.dumps({
            "description": description,
            "minutes": minutes,
            "when": self._when.isoformat(),
            "type": event_type,
            "project": self._tt_project_id,
        })
        return payload

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "Authorization": self._auth
        }
        return headers

    def _post_payload(self, payload):
        return True  # todo send to team track
        r = requests.request(
            "POST",
            self.LOG_ENDPOINT,
            data=payload,
            headers=self._headers(),
        )


def print_log(tasks, meetings):
    print('\n')
    for event in tasks + meetings:
        print(event)
    print(('\n'))
    all_meetings_time = sum([obj.work_time for obj in meetings], timedelta())
    all_tasks_time = sum([obj.work_time for obj in tasks], timedelta())
    all_meetings_title = ", ".join([event.description for event in meetings])
    all_tasks_title = ", ".join([event.key for event in tasks])
    print('{} - {}'.format(all_tasks_time, all_tasks_title))
    print('{} - {}'.format(all_meetings_time, all_meetings_title))


def get_date_to_compare(args, timezone):
    if args.date_to_compare:
        return timezone.localize(parser.parse(args.date_to_compare))
    else:
        return datetime.now(timezone)


def is_weekend(date):
    return date.weekday() > 4


def main():
    args = parse_args()

    config_loader = ConfigLoader(CONFIG_FILE)
    config = config_loader.process_config()
    jira_config = JiraConfig(**config[JIRA])

    date_to_compare = get_date_to_compare(args, config['timezone'])
    if is_weekend(date_to_compare):
        raise TeamTrackerLoggerError('Cannot log work on weekend')
    start_work_timestamp = date_to_compare.replace(
        hour=config['i_start_work_at'], minute=0, second=0)
    stop_work_timestamp = start_work_timestamp + timedelta(hours=WORK_HOURS)

    meetings_builder = MeetingsBuilder(date_to_compare.date())
    # getter = FileTaskGetter()
    getter = JiraTaskGetter(jira_config)
    processor = JiraTaskProcessor(jira_config, date_to_compare.date(),
                                  start_work_timestamp, stop_work_timestamp)
    adjuster = TimeAdjuster()
    tt_logger = TeamTrackerLogger(config[TEAMTRACKER][TT_PROJECT_ID],
                                  config[TEAMTRACKER]['auth'],
                                  date_to_compare.date())

    if args.override_meeting:
        meetings = [args.override_meeting]
    else:
        meetings = meetings_builder.get_meetings(config[MEETINGS])
        if args.additional_meeting:
            meetings.append(args.additional_meeting)
    tasks = getter.get_tasks()
    tasks = processor.process_jira_tasks(tasks)
    tasks = adjuster.adjust_time(tasks, meetings)

    print_log(tasks, meetings)

    if args.yolo:
        print('Logging your work time to TT')
        tt_logger.post_log(tasks + meetings)
    else:
        decision = input('\nProceed with logging to TT? [Y/n]')
        if decision in ['', 'T', 't', 'Y', 'y']:
            print('Logging your work time to TT')
            tt_logger.post_log(tasks + meetings)
        elif decision in ['N', 'n', 'No', 'no']:
            print('Aborted')
        else:
            print('Unknown command')


if __name__ == "__main__":
    main()
