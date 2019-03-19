import sys
sys.path.append('../../')
import schedule
import time
from datetime import datetime, timedelta
from pytz import timezone
from flaskr import app
from flaskr import db
from flaskr.models import AutoScalingConfig, RequestPerMinute
from sqlalchemy import desc
import aws
import json

awscli = aws.AwsClient()

# get start_time and end_time of latest 1 minute
def get_time_span(latest):
    end_time = datetime.now(timezone(app.config['ZONE']))
    start_time = end_time - timedelta(seconds=latest)
    return start_time, end_time

def current_config():
    return AutoScalingConfig.query.order_by(desc(AutoScalingConfig.timestamp)).first()

def average_cpu_utils():
    valid_instances_id = awscli.get_valid_target_instances()
    l = len(valid_instances_id)
    start_time, end_time = get_time_span(600)
    cpu_sum, count = 0, 0
    for i in range(l):
        response = awscli.get_cpu_utils(valid_instances_id[i], start_time, end_time)
        response = json.loads(response)
        print(response)
        if response and response[0]:
            cpu_sum += response[0][1]
            count += 1

    return cpu_sum / count if count else -1


def auto_scaling():
    current_time = datetime.now()
    cpu_utils = average_cpu_utils()
    config = current_config()
    print('-----------auto_scaling------------')
    print(current_time)
    print(config)
    print(cpu_utils)

    # if there is no valid instances, then do nothing.
    if cpu_utils == -1:
        print('{} no workers in the pool'.format(current_time))
        return

    if not config:
        print('{} no auto scaling configuration'.format(current_time))
        return

    #cpu_grow, cpu_shrink, ratio_expand, ratio_shrink
    if cpu_utils > config.cpu_grow:
        response = awscli.grow_worker_by_ratio(config.ratio_expand)
        print('{} grow workers: {}'.format(current_time, response))
        #time.sleep(60)
    elif cpu_utils < config.cpu_shrink:
        response = awscli.shrink_worker_by_ratio(config.ratio_shrink)
        print('{} shrink workers: {}'.format(current_time, response))
        #time.sleep(60)
    else:
        print('{} nothing change'.format(current_time))


def clear_requests():
    # clear the records 2 hours ago
    start_time, end_time = get_time_span(7260)
    RequestPerMinute.query.filter(RequestPerMinute.timestamp < start_time).delete()
    db.session.commit()
    print('{} delete records two hours go'.format(end_time))


if __name__ == '__main__':
    # start auto-scaling
    schedule.every().minute.do(auto_scaling)
    schedule.every(60).minutes.do(clear_requests)
    while True:
        schedule.run_pending()
        time.sleep(1)
