#!/usr/bin/env python

import os
import argparse
from urlparse import urlparse
import redis
from termcolor import cprint

DEBUG = os.environ.get("DEBUG")
DRY_RUN = os.environ.get("DRY_RUN")
CLEAN_UP = os.environ.get("CLEAN_UP")

if os.environ.get("REPLACE_DST_KEYS"):
    REPLACE_DST_KEYS = True
else:
    REPLACE_DST_KEYS = False

def connect_redis(conn_dict):
    conn = redis.StrictRedis(host=conn_dict['host'],
                             port=conn_dict['port'],
                             db=conn_dict['db'])
    return conn


def conn_string_type(string):
    format = 'redis://<host>:<port>/<db>'
    url = urlparse(string)

    if url.scheme != "redis":
        raise argparse.ArgumentTypeError('incorrect format, should be: %s' % format)

    host = url.hostname

    if url.port:
        port = url.port
    else:
        port = "6379"

    if url.path:
        db = url.path.strip("/")
    else:
        db = "0"

    try:
        port = int(port)
        db = int(db)
    except ValueError:
        raise argparse.ArgumentTypeError('incorrect format, should be: %s' % format)

    return {'host': host,
            'port': port,
            'db': db}


def migrate_redis(source, destination):
    if DRY_RUN:
        output_color = 'yellow'
        log_suffix = ' << DRY_RUN >>'
    else:
        output_color = 'green'
        log_suffix = ''

    cprint("Migrating %s:%s/%s to %s:%s/%s...%s" % (source['host'], source['port'], source['db'], destination['host'], destination['port'], destination['db'], log_suffix), output_color)

    src = connect_redis(source)
    dst = connect_redis(destination)
    keys = src.keys('*')
    errors = 0
    for key in keys:
        ttl = src.ttl(key)
        # we handle TTL command returning -1 (no expire) or -2 (no key)
        if ttl < 0:
            ttl = 0
        if DEBUG or DRY_RUN:
            cprint("Dumping key: %s with TTL %ss%s" % (key, ttl, log_suffix), output_color)
        value = src.dump(key)
        if not DRY_RUN:
            if DEBUG:
                cprint("Restoring key: %s with TTL %sms" % (key, ttl * 1000), output_color)
            try:
                # TTL command returns the key's ttl value in seconds but restore expects it in milliseconds!
                dst.restore(key, ttl * 1000, value, replace=REPLACE_DST_KEYS)
            except (redis.exceptions.ResponseError, redis.exceptions.DataError):
                cprint("! Failed to restore key: %s" % key, 'red')
                errors += 1
                continue # Don't delete the key in src if it failed to restore - move on to the next iteration
            if CLEAN_UP:
                if DEBUG:
                    cprint("Deleting source key: %s" % key, output_color)
                src.delete(key)

    if not DRY_RUN:
        cprint("Migrated %d keys" % (len(keys) - errors), output_color)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=conn_string_type)
    parser.add_argument('destination', type=conn_string_type)
    options = parser.parse_args()
    migrate_redis(options.source, options.destination)

if __name__ == '__main__':
    run()
