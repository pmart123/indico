# This file is part of Indico.
# Copyright (C) 2002 - 2017 European Organization for Nuclear Research (CERN).
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# Indico is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Indico; if not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

from flask import session

from indico.core import signals
from indico.core.db import db
from indico.modules.events.logs.models.entries import EventLogRealm, EventLogKind
from indico.modules.events.sessions import logger
from indico.modules.events.sessions.models.sessions import Session
from indico.modules.events.sessions.models.blocks import SessionBlock


def create_session(event, data):
    """Create a new session with the information passed in the `data` argument"""
    event_session = Session(event_new=event)
    event_session.populate_from_dict(data)
    db.session.flush()
    event.log(EventLogRealm.management, EventLogKind.positive, 'Sessions',
              'Session "{}" has been created'.format(event_session.title), session.user)
    logger.info('Session %s created by %s', event_session, session.user)
    return event_session


def create_session_block(session_, data):
    block = SessionBlock(session=session_)
    block.populate_from_dict(data)
    db.session.flush()
    session_.event_new.log(EventLogRealm.management, EventLogKind.positive, 'Sessions',
                           'Session block "{}" for session "{}" has been created'
                           .format(block.title, session_.title), session.user)
    logger.info("Session block %s created by %s", block, session.user)
    return block


def update_session(event_session, data):
    """Update a session based on the information in the `data`"""
    event_session.populate_from_dict(data)
    db.session.flush()
    signals.event.session_updated.send(event_session)
    event_session.event_new.log(EventLogRealm.management, EventLogKind.change, 'Sessions',
                                'Session "{}" has been updated'.format(event_session.title), session.user)
    logger.info('Session %s modified by %s', event_session, session.user)


def _delete_session_timetable_entries(event_session):
    for block in event_session.blocks:
        for contribution in block.contributions:
            if contribution.timetable_entry:
                db.session.delete(contribution.timetable_entry)
        if not block.timetable_entry:
            continue
        for child_block in block.timetable_entry.children:
            db.session.delete(child_block)
        db.session.delete(block.timetable_entry)


def delete_session(event_session):
    """Delete session from the event"""
    event_session.is_deleted = True
    for contribution in event_session.contributions[:]:
        contribution.session = None
    _delete_session_timetable_entries(event_session)
    signals.event.session_deleted.send(event_session)
    logger.info('Session %s deleted by %s', event_session, session.user)


def update_session_block(session_block, data):
    """Update a session block with data passed in the `data` argument"""
    from indico.modules.events.timetable.operations import update_timetable_entry

    start_dt = data.pop('start_dt', None)
    if start_dt is not None:
        session_block.timetable_entry.move(start_dt)
        update_timetable_entry(session_block.timetable_entry, {'start_dt': start_dt})
    session_block.populate_from_dict(data)
    db.session.flush()
    session_block.event_new.log(EventLogRealm.management, EventLogKind.change, 'Sessions',
                                'Session block "{}" has been updated'.format(session_block.title), session.user)
    logger.info('Session block %s modified by %s', session_block, session.user)


def delete_session_block(session_block):
    from indico.modules.events.timetable.operations import delete_timetable_entry
    session_ = session_block.session
    for contribution in session_block.contributions[:]:
        contribution.session_block = None
        delete_timetable_entry(contribution.timetable_entry, log=False)
    for entry in session_block.timetable_entry.children[:]:
        delete_timetable_entry(entry, log=False)
    delete_timetable_entry(session_block.timetable_entry, log=False)
    signals.event.session_block_deleted.send(session_block)
    if session_block in session_.blocks:
        session_.blocks.remove(session_block)
    if not session_.blocks and session_.event_new.type != 'conference':
        delete_session(session_)
    db.session.flush()
    logger.info('Session block %s deleted by %s', session_block, session.user)
