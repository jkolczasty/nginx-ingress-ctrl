#!/usr/bin/python3
#
# nginx ingress helper
#
# (c) <jkolczasty@gmail.com>
#

import argparse
import logging
import os
import mako
import mako.template
import mako.lookup

import time
import re
import subprocess
import signal
import json
import socket
from pprint import pprint

TEMPLATE_PATHS = ["/templates", "/ingress/templates", ]
CONFIG_PATH_DEF = "/config"
NGINX_CONFIG_PATH_DEF = "/etc/nginx/http.d"
NGINX_RENDER_OUTPUT_DEF = "/etc/nginx/vhosts.d"


def dump_data(obj, filename):
    with open(filename, 'w', encoding='utf8') as f:
        pprint(obj, f)


def dump_data_json(obj, filename):
    with open(filename, 'w', encoding='utf8') as f:
        json.dump(obj, f, indent=4)


def dpath_simple(obj, path):
    _obj = obj

    for p in path:
        # noinspection PyBroadException
        try:
            _obj = _obj.get(p)
        except:
            return None

    return _obj


def read_file_config_simple(filepath):
    data = {}
    with open(filepath, 'r', encoding='utf8') as f:
        for line in f:
            _l = line.strip()
            la = _l.split(":", 1)
            if len(la) != 2:
                continue
            data[la[0].strip()] = la[1].strip()

    return data


class NginxController(object):
    def __init__(self, nginx_config_path, render_output):
        self._need_reload = False
        self.proc = None
        self.log = logging.getLogger("nginx")
        self.nginx_config_path = nginx_config_path
        self.render_output = render_output

    def config_gen_include_config(self):
        fn = os.path.join(self.nginx_config_path, "ingress-include.conf")
        ifn = os.path.join(self.render_output, "*.conf")

        with open(fn, 'w', encoding='utf8') as f:
            f.write(f"include {ifn};\n")

    def service_config_save(self, name, body):
        fn = os.path.join(self.render_output, f'{name}.conf')
        with open(fn, 'w', encoding='utf8') as f:
            f.write(body)

        self.need_reload()

    def prepare(self):
        self.config_gen_include_config()

    def start(self):
        if self.proc:
            return

        cmd = ['nginx', '-c', '/etc/nginx/nginx.conf', '-g', 'daemon off;']
        args = dict()  # , stdout=subprocess.STDOUT, stderr=subprocess.STDOUT)
        self.log.info("Starting nginx")
        self.proc = subprocess.Popen(cmd, **args)
        self.log.info("Nginx PID: %d", self.proc.pid)

    def check(self):
        if not self.proc:
            self.start()
            # so if it starts, no need to reload
            self._need_reload = False

        if self.proc.poll() is None:
            self.reload_if_needed()
            return True

        ec = self.proc.returncode

        self.log.info("nginx exit: %d", ec)
        self.proc = None

        return ec <= 0

    def terminate(self):
        if self.proc:
            self.proc.terminate()

    def need_reload(self):
        self._need_reload = True

    def reload(self):
        self.check()

        self.log.info("Reloading nginx")

        try:
            subprocess.check_call(['nginx', '-c', '/etc/nginx/nginx.conf', '-t'])
        except Exception as e:
            self.log.error("nginx test failed, aborting reload: %s: %s", e.__class__.__name__, e)
            return

        self.proc.send_signal(signal.SIGHUP)

    def reload_if_needed(self):
        if not self._need_reload:
            return

        self._need_reload = False
        self.reload()


class NginxConfig(object):
    name = None
    template = None
    hostname = None

    _params = None

    _active = None
    _ips = None
    _backend_ip = None

    _watch_files = None
    _monitor_ip = True
    changed = True

    def __init__(self, name, template, hostname, params):
        self.log = logging.getLogger(f"config.{name}")
        self.name = name
        self.template = template
        self.hostname = hostname
        self._params = params
        self._watch_files = {}
        backend_ip = params.get('backend.ip')
        self._backend_ip = backend_ip
        if backend_ip:
            self._ips = backend_ip
            self._monitor_ip = False
            self.active = True

    @classmethod
    def from_file(cls, filename):
        name = os.path.basename(filename).rsplit(".", 1)[0]
        params = read_file_config_simple(filename)
        template = params.get('template')
        if not template:
            raise ValueError("Missing template")
        backend_host = params.get('backend.host')
        if not backend_host:
            raise ValueError("Missing backend.host")

        return cls(name, template, backend_host, params)

    def check(self):
        # TODO: support multiple IPS
        # noinspection PyBroadException

        for fn, cmt in self._watch_files.items():
            if os.path.isfile(fn):
                mt = os.path.getmtime(fn)
            else:
                mt = 0

            if cmt != mt:
                self.log.info("Changed by watch file: %s", fn)
                self.changed = True

        if self._monitor_ip:
            try:
                socket.setdefaulttimeout(3)
                ip = socket.gethostbyname(self.hostname)
            except Exception:
                ip = None

            self.active = True if ip else False

            _ips = [ip] if ip else None
            changed = _ips != self._ips
            if changed:
                self.log.info("IP: %s", ip)
                self._ips = _ips
                self.changed = True
                return

        return

    def watch_file(self, path):
        if os.path.isfile(path):
            mt = os.path.getmtime(path)
        else:
            mt = 0

        self._watch_files[path] = mt

        return path

    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, value: bool):
        if self._active == value:
            return

        self.log.info("Changed by: active: %s", value)
        self._active = value
        self.changed = True

    @property
    def params(self):
        return self._params

    @params.setter
    def params(self, params):
        if params == self._params:
            return

        self.log.info("Changed by: labels")

        self._params = params
        self.changed = True

    @property
    def ipaddress(self):
        _ips = self._ips
        return _ips if _ips else None

    def get_param(self, name, default=''):
        v = self._params.get(name)
        if not v:
            return default
        return v

    def get_param_int(self, name, default=0):
        v = self._params.get(name)
        if not v:
            return default
        # noinspection PyBroadException
        try:
            return int(v)
        except:
            return default

    def get_param_bool(self, name, default=False):
        v = self._params.get(name)
        if not v:
            return default

        if v in ('on', '1', 'yes', 'true'):
            return True
        if v in ('off', '0', 'no', 'false'):
            return False

        return default

    def get_param_onoff(self, name, default=0):
        v = self._params.get(name)
        if v in ('on', 'off'):
            return v
        return default

    def get_first_ip(self):
        if not self._ips:
            return "127.0.0.1"

        return self._ips[0]

    def get_backend_port(self, default='8000'):
        return self._params.get('backend.port') or default

    def get_backend_static_ip(self, default=None):
        return self._params.get('backend.ip') or default

    def get_backend_schema(self, default='http'):
        return self._params.get('backend.schema') or default

    def get_http_hostname(self, default='unknown.host.tld'):
        return self._params.get('http.host') or default

    def get_http_port(self, default=80):
        port = self._params.get('http.port')
        if not port:
            return default
        # noinspection PyBroadException
        try:
            return int(port)
        except:
            return default


class RenderContextError(Exception):
    pass


class RenderContext(object):
    def __init__(self):
        self.valid = True

    def slug(self, s):
        slug = s.encode('ascii', 'ignore').lower().decode('ascii')
        slug = re.sub(r'[^a-z0-9]+', '_', slug).strip('_')
        return re.sub(r'[_]+', '_', slug)

    def require_file(self, path):
        if not os.path.isfile(path):
            raise RenderContextError(f"Missing file: {path}")
        return path


class IngressController(object):
    log = None

    def __init__(self, config_path, nginx_config_path, nginx_config_render_path):
        self.log = logging.getLogger("ingress")
        self.log = logging.getLogger("ingress")
        self.nginx = NginxController(nginx_config_path, nginx_config_render_path)
        self.config_path = config_path
        self._shutdown = False
        self._configs = {}

        self.templates = mako.lookup.TemplateLookup(directories=TEMPLATE_PATHS)

    def shutdown(self):
        self._shutdown = True

    def configs_load(self):
        config_path = self.config_path
        self.log.info("Read configs from: %s", config_path)
        for fn in os.listdir(config_path):
            if not fn.endswith('.conf'):
                continue
            self.log.info("Read config: %s", fn)
            ffn = os.path.join(config_path, fn)
            cfg = NginxConfig.from_file(ffn)
            self._configs[fn] = cfg

    def configs_check(self):
        for name, config in self._configs.items():
            config.check()
            if config.changed:
                self.nginx_config_render(config)

    def nginx_config_render(self, config):
        config.changed = False

        template = config.template
        if not template:
            return

        name = config.name

        try:
            ctx = RenderContext()
            t = self.templates.get_template(f'{template}.tmpl')
            data = dict(name=name, config=config, params=config.params, ctx=ctx, result={})

            s = t.render(**data)

            self.nginx.service_config_save(name, s)
        except RenderContextError as e:
            self.log.error(f"Failed to render template for: %s: %s: %s", name, e.__class__.__name__, e)
        except Exception as e:
            self.log.exception(f"Failed to render template for: %s: %s: %s", name, e.__class__.__name__, e)

    def _run(self):
        c = 1000000
        self.configs_check()
        self.nginx.prepare()

        while not self._shutdown:
            time.sleep(0.1)
            c += 1
            if c > 1000:
                c = 0

            if c % 100 == 0:
                self.configs_check()

            if c % 10 == 0:
                if not self.nginx.check():
                    self.log.info("Nginx failed")
                    self._shutdown = True

        self.log.info("Exiting")

    def run(self):
        # noinspection PyBroadException
        try:
            self.configs_load()
            self._run()
        except Exception:
            self.log.exception("Exception")

        self.nginx.terminate()


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog='ingress')
    parser.add_argument('--config-path', default=CONFIG_PATH_DEF)
    parser.add_argument('--nginx-config-path', default=NGINX_CONFIG_PATH_DEF)
    parser.add_argument('--nginx-config-render-path', default=NGINX_RENDER_OUTPUT_DEF)

    args = parser.parse_args()

    ctrl = IngressController(args.config_path, args.nginx_config_path, args.nginx_config_render_path)

    def signal_handler(signum, frame):
        print('Signal handler called with signal', signum)
        ctrl.shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    ctrl.run()


main()
