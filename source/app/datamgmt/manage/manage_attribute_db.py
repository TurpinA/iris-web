#!/usr/bin/env python3
#
#  IRIS Source Code
#  Copyright (C) 2021 - Airbus CyberSecurity (SAS)
#  ir@cyberactionlab.net
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
import json

import logging as logger
from sqlalchemy.orm.attributes import flag_modified

from app import db
from app.models import Ioc, CustomAttribute, CasesEvent, CaseAssets, CaseTasks, Notes, CaseReceivedFile

log = logger.getLogger(__name__)


def update_all_attributes(object_type):

    obj_list = []
    if object_type == 'ioc':
        obj_list = Ioc.query.all()
    elif object_type == 'event':
        obj_list = CasesEvent.query.all()
    elif object_type == 'asset':
        obj_list = CaseAssets.query.all()
    elif object_type == 'task':
        obj_list = CaseTasks.query.all()
    elif object_type == 'note':
        obj_list = Notes.query.all()
    elif object_type == 'evidence':
        obj_list = CaseReceivedFile.query.all()

    ioc_attr = CustomAttribute.query.with_entities(
        CustomAttribute.attribute_content
    ).filter(
        CustomAttribute.attribute_for == object_type
    ).first()

    target_attr = ioc_attr.attribute_content

    print(f'Migrating {len(obj_list)} objects of type {object_type}')
    for obj in obj_list:

        for tab in target_attr:
            if obj.custom_attributes is None:
                obj.custom_attributes = target_attr
                flag_modified(obj, "custom_attributes")
                continue

            if obj.custom_attributes.get(tab) is None:
                print(f'Migrating {tab}')
                flag_modified(obj, "custom_attributes")
                obj.custom_attributes[tab] = target_attr[tab]

            else:
                for element in target_attr[tab]:
                    if element not in obj.custom_attributes[tab]:
                        print(f'Migrating {element}')
                        flag_modified(obj, "custom_attributes")
                        obj.custom_attributes[tab][element] = target_attr[tab][element]

                    else:
                        if obj.custom_attributes[tab][element]['type'] != target_attr[tab][element]['type']:
                            flag_modified(obj, "custom_attributes")
                            obj.custom_attributes[tab][element]['type'] = target_attr[tab][element]['type']

                        if obj.custom_attributes[tab][element]['mandatory'] != target_attr[tab][element]['mandatory']:
                            flag_modified(obj, "custom_attributes")
                            obj.custom_attributes[tab][element]['mandatory'] = target_attr[tab][element]['mandatory']

        # Commit will only be effective if we flagged a modification, reducing load on the DB
        db.session.commit()


def get_default_custom_attributes(object_type):
    ca = CustomAttribute.query.filter(CustomAttribute.attribute_for == object_type).first()
    return ca.attribute_content


def merge_custom_attributes(data, obj_id, object_type):

    obj = None
    if obj_id:
        if object_type == 'ioc':
            obj = Ioc.query.filter(Ioc.ioc_id == obj_id).first()
        elif object_type == 'event':
            obj = CasesEvent.query.filter(CasesEvent.event_id == obj_id).first()
        elif object_type == 'asset':
            obj = CaseAssets.query.filter(CaseAssets.asset_id == obj_id).first()
        elif object_type == 'task':
            obj = CaseTasks.query.filter(CaseTasks.id == obj_id).first()
        elif object_type == 'note':
            obj = Notes.query.filter(Notes.note_id == obj_id).first()
        elif object_type == 'evidence':
            obj = CaseReceivedFile.query.filter(CaseReceivedFile.id == obj_id).first()

        if not obj:
            return data

        for tab in data:
            if obj.custom_attributes.get(tab) is None:
                log.error(f'Missing tab {tab} in {object_type}')
                continue

            for field in data[tab]:
                if field not in obj.custom_attributes[tab]:
                    log.error(f'Missing field {field} in {object_type}')

                else:
                    if obj.custom_attributes[tab][field]['value'] != data[tab][field]:
                        flag_modified(obj, "custom_attributes")
                        obj.custom_attributes[tab][field]['value'] = data[tab][field]

        # Commit will only be effective if we flagged a modification, reducing load on the DB
        db.session.commit()
        return obj.custom_attributes

    else:
        default_attr = get_default_custom_attributes(object_type)
        for tab in data:
            if default_attr.get(tab) is None:
                print(f'Missing tab {tab} in {object_type} default attribute')
                continue

            for field in data[tab]:
                if field not in default_attr[tab]:
                    print(f'Missing field {field} in {object_type} default attribute')

                else:
                    default_attr[tab][field]['value'] = data[tab][field]

        return default_attr


def validate_attribute(attribute):
    logs = []
    try:
        data = json.loads(attribute)
    except Exception as e:
        return None, [str(e)]

    for tab in data:
        for field in data[tab]:
            if not data[tab][field].get('type'):
                logs.append(f'{tab}::{field} is missing mandatory "type" tag')
                continue

            field_type = data[tab][field].get('type')
            if field_type in ['input_string', 'input_textfield', 'input_checkbox']:
                if data[tab][field].get('mandatory') is None:
                    logs.append(f'{tab} -> {field} of type {field_type} is missing mandatory "mandatory" tag')

                elif not isinstance(data[tab][field].get('mandatory'), bool):
                    logs.append(f'{tab} -> {field} -> "mandatory" expects a value of type bool, '
                                f'but got {type(data[tab][field].get("mandatory"))}')

                if data[tab][field].get('value') is None:
                    logs.append(f'{tab} -> {field} of type {field_type} is missing mandatory "value" tag')

                if field_type == 'input_checkbox' and not isinstance(data[tab][field].get('value'), bool):
                    logs.append(f'{tab} -> {field} of type {field_type} expects a value of type bool, '
                                f'but got {type(data[tab][field].get("value"))}')

            elif field_type in ['raw', 'html']:
                if data[tab][field].get('value') is None:
                    logs.append(f'{tab} -> {field} of type {field_type} is missing mandatory "value" tag')

            else:
                logs.append(f'{tab} -> {field}, unknown field type "{field_type}"')

    return dict(data), logs