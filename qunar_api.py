# -*- coding: utf-8 -*-
"""
@author demo <dongxlmo@163.com>
@file: mt_api.py
@time 2018/8/10 下午3:31
"""

import base64
import json
import urllib
import hashlib
import datetime
import requests
import logging
import xmltodict
import platform
from mjtt_django.settings import qunar_order_conf


logger = logging.getLogger("mjtt.qunar_api")


def parse_xml(body_dict):
    """
    解析xml
    :param xml_str:
    :return:
    """
    data_str = base64.b64decode(body_dict['data'])
    data_dict = xmltodict.parse(data_str)
    if data_dict.has_key('request'):
        header_data = data_dict['request']['header']
        body_data = data_dict['request']['body']
    elif data_dict.has_key('response'):
        header_data = data_dict['response']['header']
        body_data = None
    else:
        raise ValueError('request or response data parse error')
    return header_data, body_data


def generate_xml(data, is_response=True):
    """
    生成xml  data dict
    :return:
    """
    res_attribute = {
        "@xsi:schemaLocation": qunar_order_conf['xsi:schemaLocation'] if is_response else qunar_order_conf[
            'req-xsi:schemaLocation'],
        "@xmlns": qunar_order_conf['xmlns'] if is_response else qunar_order_conf['req-xmlns'],
        "@xmlns:xsi": qunar_order_conf['xmlns:xsi'],
    }
    header = {
        "application": 'Qunar.Menpiao.Agent',
        "processor": 'SupplierDataExchangeProcessor',
        "version": 'v2.1.5',
        "bodyType": data['bodyType'],
        "createUser": qunar_order_conf['supplierIdentity'],
        "createTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if is_response:
        header.update({"code": data['code'], "describe": data['msg']}.copy())
    else:
        header.update({"supplierIdentity": qunar_order_conf['supplierIdentity']}.copy())

    body = {"@xsi:type": data['bodyType']}
    body.update(dict(data['res_data']).copy())

    xml_dict = {'response': {'header': header, 'body': body}}
    xml_dict['response'].update(dict(res_attribute).copy())
    xml = xmltodict.unparse(xml_dict, encoding='UTF-8', pretty=True)
    return xml


class QunarOrderClient(object):

    def __init__(self, conf):
        self.conf = conf

    def _check_supplierIdentity(self, supplierIdentity):
        if self.conf["supplierIdentity"] == supplierIdentity:
            return True
        else:
            logger.error("supplierIdentity error, v_supplierIdentity: %s, supplierIdentity: %s" %
                         (self.conf["supplierIdentity"], supplierIdentity))
            return False

    def _check_sign(self, data, sign):
        v_sign = self.build_sign(data)
        if v_sign.lower() == sign.lower():
            return True
        else:
            logger.error('sign error, v_sign: %s, sign: %s' % (v_sign, sign))
            return False

    def build_sign(self, data):
        data = data.replace("\r\n", "").replace("\n", "").replace("\r", "")
        return hashlib.md5((self.conf['signkey'] + data).encode('utf-8')).hexdigest()

    def str_to_dict(self, body_str):
        method = urllib.unquote_plus(body_str).split('&request')[0].split('method=')[1]
        body_dict = json.loads(urllib.unquote_plus(body_str).split('&request')[1].split('Param=')[1])
        return method, body_dict

    def get_heart_params(self, body_str):
        method, body_dict = self.str_to_dict(body_str)
        header, body = parse_xml(body_dict)
        if not self._check_supplierIdentity(header['supplierIdentity']):
            raise ValueError("supplierIdentity error")
        if not body:
            raise ValueError("get header error")
        return body

    def get_common_params(self, body_str):
        method, body_dict = self.str_to_dict(body_str)
        if not self._check_sign(body_dict['data'], body_dict["signed"]):
            raise ValueError("signed error")

        header, body = parse_xml(body_dict)
        logger.info('params: %s--%s' % (header, body))
        return method, body

    def gen_response(self, code, body_num, res_data=None, msg=None):
        if body_num == 1:
            body_type = self.conf['create_order_response_bodytype']
        elif body_num == 2:
            body_type = self.conf['push_order_response_bodytype']
        elif body_num == 3:
            body_type = self.conf['pay_order_response_bodytype']
        elif body_num == 4:
            body_type = self.conf['refund_order_response_bodytype']
        elif body_num == 5:
            body_type = self.conf['get_order_response_bodytype']
        else:
            body_type = self.conf['send_eticket_response_bodytype']

        data = {
            'code': code,
            'msg': msg,
            'bodyType': body_type,
            'res_data': res_data if res_data else ''
        }
        xml = generate_xml(data)
        bs64_data = base64.b64encode(xml)
        result = {
            'data': bs64_data,
            'signed': self.build_sign(bs64_data),
            'securityType': 'MD5'
        }

        if code != 1000:
            logger.error("QUNAER ORDER RESPONSE ERROR: %s" % msg)
        return result

    def sync_order_status(self, res_data, body_num):
        if body_num == 10:
            body_type = self.conf['sended_eticket_request_bodytype']
            method = self.conf['sended_eticket_request_method']
        else:
            body_type = self.conf['consumed_order_request_bodytype']
            method = self.conf['consumed_order_request_method']

        post_data = {
            "res_data": res_data,
            "bodyType": body_type
        }
        xml_str = generate_xml(post_data, is_response=False)
        b64_data = base64.b64encode(xml_str)
        data = {
            "data": b64_data,
            "signed": self.build_sign(b64_data),
            "securityType": "MD5"
        }
        data = 'requestParam=' + urllib.quote_plus(json.dumps(data))

        try:
            url = self.conf['push_url'] + '?method=' + method + '&' + data
            resp = requests.get(url)
        except Exception as e:
            logger.error("QUNAER ORDER SYNC ERROR: %s" % str(e))
            return False

        header, _ = parse_xml(resp.json())
        if resp.status_code == 200 and header['code'] == '1000':
            return True
        else:
            logger.error("QUNAER ORDER SYNC DATA: %s" % data)
            return False
