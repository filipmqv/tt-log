# tt-log
Automatically log your work time to TeamTracker with one command.

You can run the script `tt-log.py` using python or use the version build for Linux in `dist` directory: `cd dist` -> `./tt-log`.
Setup:
1. Copy file `tt-log-config.json.template` with new name, which should be `tt-log-config.json` (remove `.template` part).
2. If you want to run build version - copy `tt-log-config.json` to `dist` directory.
3. Fill the config file with neccessary data.
 * Meetings:
    * In `"meetings"` object you can set your regular meetings. `"work_time"` is in minutes.
    * Daily events are the ones that you have every day. You can put more of them on the list or simply write them all in one title.
    * If you have weekly sprint (and events occuring every week) - set `"sprint"` field to `"weekly"` and write events on `"weekly_events"` list. There is one object per day - first for Monday, second for Tuesday etc.
    * If you have sprints that last 2 weeks - set `"sprint"` field to `"biweekly"` and write events on `"biweekly_events"` list. First 5 are for first week, other for second week. Set `"biweekly_start_date"` to be the date of Monday in first week. This date must be in the past!
  * TeamTracker:
    * for `"auth"` replace `real_token` with token from TeamTracker. It will be available once the API will work.
    * for `"tt_project_id"` set proper project ID from TeamTracker - it is available in URL when you enter your project details page.
  * Other:
    * change `"timezone"` if you work outside of Poland
    * set `"i_start_work_at"` to be the hour you start work at (only full hours)


```json
{
  "jira": {
    "username": "usually it is your email address used to register to Jira",
    "password": "password to Jira",
    "assignee_name": "usually your first and last name joined with dot, without polish letters (imie.nazwisko). Check Jira @mention to be sure.",
    "project_abbr": "letters that appear in task key eg. ABC for task ABC-1234",
    "status_field": "name of field that contains status of task",
    "start_work_status": "In Progress  # status of work in progress",
    "stop_work_status_primary": "CODE REVIEW  # status of finishing work",
    "stop_work_status_secondary": "QA  # alternative status of finishing work",
  },
  "meetings": {
    "daily_events": [  
      {
        "title": "daily",
        "work_time": 15
      }
    ],
    "sprint": "weekly or biweekly - put one of those",
    "weekly_events": [
      {
        "title": "monday",
        "work_time": 60
      },
      {
        "title": "retro",
        "work_time": 90
      },
      {
        "title": "planning",
        "work_time": 120
      },
      {
        "title": "anything",
        "work_time": 45
      },
      {
        "title": "",
        "work_time": 0
      }
    ],

    "biweekly_start_date": "2019-01-14",
    "biweekly_events": [
      {
        "title": "",
        "work_time": 0
      },
      {
        "title": "",
        "work_time": 0
      },
      {
        "title": "",
        "work_time": 0
      },
      {
        "title": "",
        "work_time": 0
      },
      {
        "title": "friday",
        "work_time": 0
      },

      {
        "title": "monday",
        "work_time": 0
      },
      {
        "title": "",
        "work_time": 0
      },
      {
        "title": "",
        "work_time": 0
      },
      {
        "title": "",
        "work_time": 0
      },
      {
        "title": "",
        "work_time": 0
      }
    ]
  },
  "teamtracker": {
    "auth": "Token real_token",
    "tt_project_id": 1
  },
  "timezone": "Europe/Warsaw",
  "i_start_work_at": 9
}
```
4. Run the script form the directory that the script resides in (so it can "see" the config file):
 * `python tt-log.py` or
 * (being in `dist` directory) `./tt-log`
 
 By default it will log time for present day.
5. You can inspect optional args by invoking `python tt-log.py --help`
