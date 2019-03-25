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
NAME = 'name'

MEETINGS = 'meetings'
DAILY_EVENTS = 'daily_events'
WEEKLY_EVENTS = 'weekly_events'
BIWEEKLY_EVENTS = 'biweekly_events'


class TeamTrackerLoggerError(Exception):
    pass


def make_parser():
    arg_parser = ArgumentParser('Log work time to TeamTracker')

    arg_parser.add_argument('-w', '--when', dest='date_to_compare', type=str,
                            help='Provide date for which you want to log work in ISO date format "YYYY-MM-DD"')
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
                work_time=timedelta(minutes=int(work_time)),
                event_type=EventType.MEETING,
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


@attr.dataclass(repr=False, frozen=True)
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


@attr.dataclass(frozen=True)
class TimeInterval:
    start: datetime
    stop: datetime
    from_status: str
    to_status: str

    def is_between(self, timestamp: date) -> bool:
        """
        Checks if timestamp is between start and stop dates
        """
        return self.start.date() <= timestamp <= self.stop.date()

    @property
    def duration(self):
        return self.stop - self.start


@attr.dataclass(frozen=True)
class StatusChange:
    created: datetime
    to_status: str


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

        # with open('results-full.json', 'w') as file:
        #     file.write(json.dumps(data))
        #     print('done')

        return data


@attr.dataclass
class JiraTaskProcessor:
    _config: JiraConfig
    _date_to_compare: date
    _start_work_timestamp: datetime
    _stop_work_timestamp: datetime

    _not_finished = 'NOT FINISHED YET'

    def process_jira_tasks(self, data):
        data = self._get_tasks_for_assignee(data, self._config.assignee_name)
        data = [self._process_task(obj)
                for obj in data if
                self._has_mandatory_fields(obj)]

        data = self._remove_duplicates_and_errors(data)
        return data

    @staticmethod
    def _get_tasks_for_assignee(data, assignee):
        """
        Ensures that only tasks for assignee will be processed
        """
        return [obj for obj in data['issues'] if
                obj[FIELDS] and
                obj[FIELDS][ASSIGNEE] and
                obj[FIELDS][ASSIGNEE][NAME] == assignee]

    @staticmethod
    def _remove_duplicates_and_errors(events: List[Event]) -> List[Event]:
        """
        Removes duplicates and events with work_time == None
        """
        return list(set([event for event in events if event.work_time]))

    def _has_mandatory_fields(self, obj) -> bool:
        return obj[CHANGELOG] and \
               obj[CHANGELOG][HISTORIES] and \
               obj[FIELDS] and \
               obj[FIELDS][self._config.status_field] and \
               obj[FIELDS][self._config.status_field][NAME]

    def _current_status(self, issue):
        return issue[FIELDS][self._config.status_field][NAME]

    def _process_task(self, issue):
        histories = issue[CHANGELOG][HISTORIES]
        key = issue[KEY]
        title = issue[FIELDS][SUMMARY]
        current_status = self._current_status(issue)

        on_date = self._intervals_on_date(histories, current_status)

        limited_by_work_hours = [TimeInterval(
            start=obj.start if obj.start > self._start_work_timestamp else \
                self._start_work_timestamp,
            stop=obj.stop if obj.stop < self._stop_work_timestamp or \
                             self._stop_work_timestamp < obj.start else \
                self._stop_work_timestamp,
            from_status=obj.from_status,
            to_status=obj.to_status
        ) for obj in on_date]

        durations = [obj.duration for obj in limited_by_work_hours]

        work_time = sum(durations, timedelta())

        return Event(work_time=work_time, key=key, title=title,
                     event_type=EventType.TASK)

    def _intervals_on_date(self, histories,
                           current_status: str) -> List[TimeInterval]:
        status_changes_list = self._status_changes_list(histories)
        work_intervals = self._work_intervals(status_changes_list,
                                              current_status)
        on_date = [obj for obj in work_intervals if
                   obj.is_between(self._date_to_compare)]
        return on_date

    def _work_intervals(self, changes: List[StatusChange],
                        current_status: str) -> List[TimeInterval]:
        """
        Returns TimeIntervals of actual work - they start and finish with
        proper statuses identifying start and stop work
        """
        if not changes:
            return []
        start_status = self._config.start_work_status
        stop_statuses = [self._config.stop_work_status_primary,
                         self._config.stop_work_status_secondary]
        result = []
        for start, stop in zip(changes, changes[1:]):
            if start.to_status == start_status and \
                    stop.to_status in stop_statuses:
                result.append(TimeInterval(
                    start.created, stop.created,
                    start.to_status, stop.to_status))
        last = changes[-1]
        if current_status == start_status and last.to_status == start_status:
            stop_timestamp = self._stop_work_timestamp if \
                self._stop_work_timestamp > last.created else \
                last.created + timedelta(minutes=10)
            stop = StatusChange(stop_timestamp, self._not_finished)
            result.append(
                TimeInterval(last.created, stop.created,
                             last.to_status, stop.to_status))
        return result

    def _is_status_history(self, obj) -> bool:
        """ Checks if object represents status change (not comment or other
        field update) """
        return obj[ITEMS] and obj[ITEMS][0] and obj[ITEMS][0][
            FIELD] == self._config.status_field

    def _status_changes_list(self, histories) -> List[StatusChange]:
        return [StatusChange(created=parser.parse(obj[CREATED]),
                             to_status=obj[ITEMS][0][TO_STRING])
                for obj in reversed(histories) if self._is_status_history(obj)]


class TimeAdjuster:
    def adjust_time(self, tasks: List[Event],
                    meetings: List[Event]) -> List[Event]:
        workday_hours = timedelta(hours=WORK_HOURS)
        all_meetings_time = sum([obj.work_time for obj in meetings],
                                timedelta())
        all_tasks_time = sum([obj.work_time for obj in tasks], timedelta())
        if all_tasks_time == timedelta(seconds=0):
            raise TeamTrackerLoggerError('No tasks to log')
        tasks_must_be_time = workday_hours - all_meetings_time
        tasks_times = [obj.work_time for obj in tasks]
        tasks_times = self._calculate_tasks_times(tasks_times,
                                                  tasks_must_be_time)
        tasks = self._apply_new_work_time(tasks, tasks_times)
        return tasks

    def _calculate_tasks_times(
            self,
            tasks_times: List[timedelta],
            tasks_must_be_time: timedelta
    ) -> List[timedelta]:
        """
        Calculates proportions of tasks by work time and adjusts work time
        to be tasks_must_be_time in total. Takes care of rounding.
        :return: list of timedeltas that sum up to tasks_must_be_time
        """
        proportions = self._proportions(tasks_times)
        tasks_times = [tasks_must_be_time * p for p in proportions]
        tasks_times = [self._round_timedelta(r) for r in tasks_times]
        calculated_tasks_time = sum(tasks_times, timedelta())
        diff_after_rounding = tasks_must_be_time - calculated_tasks_time
        if diff_after_rounding > timedelta(seconds=0):
            time_idx = tasks_times.index(min(tasks_times))
        else:
            time_idx = tasks_times.index(max(tasks_times))
        tasks_times[time_idx] += diff_after_rounding
        return tasks_times

    @staticmethod
    def _apply_new_work_time(tasks: List[Event], tasks_times: List[timedelta]):
        new_tasks = []
        for task, new_work_time in zip(tasks, tasks_times):
            new_tasks.append(Event(
                work_time=new_work_time,
                key=task.key,
                title=task.title,
                event_type=task.event_type
            ))
        return new_tasks

    @staticmethod
    def _round_timedelta(td: timedelta,
                         period=timedelta(minutes=5)) -> timedelta:
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


def handle_yolo_with_no_tasks(project) -> List[Event]:
    return [Event(
        key=f'working on project {project}',
        work_time=timedelta(hours=2)  # whatever to adjust later
    )]


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
    meetings = [event for event in meetings if event.work_time]
    tasks = getter.get_tasks()
    tasks = processor.process_jira_tasks(tasks)

    if args.yolo:
        all_tasks_time = sum([obj.work_time for obj in tasks], timedelta())
        if all_tasks_time == timedelta(seconds=0):
            tasks = handle_yolo_with_no_tasks(jira_config.project_abbr)

    tasks = adjuster.adjust_time(tasks, meetings)

    print_log(tasks, meetings)

    if args.yolo:
        print('Logging your work time to TT')
        tt_logger.post_log(tasks + meetings)
        print('Logged time to TT')
    else:
        decision = input('\nProceed with logging to TT? [Y/n]')
        if decision in ['', 'T', 't', 'Y', 'y', 'Tak', 'tak', 'Yes', 'yes']:
            print('Logging your work time to TT')
            tt_logger.post_log(tasks + meetings)
            print('Logged time to TT')
        elif decision in ['N', 'n', 'No', 'no']:
            print('Aborted')
        else:
            print('Unknown command')


if __name__ == "__main__":
    main()
