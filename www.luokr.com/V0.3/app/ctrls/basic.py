#coding=utf-8

import time
import functools
import tornado.web, tornado.httputil, tornado.escape
import sqlite3

try:
    import urlparse  # py2
except ImportError:
    import urllib.parse as urlparse  # py3

try:
    from urllib import urlencode  # py2
except ImportError:
    from urllib.parse import urlencode  # py3

from lib.cache import Cache
from lib.utils import Utils
from lib.recaptcha.client.captcha import submit
from app.model.admin import AdminModel
from app.model.alogs import AlogsModel
from app.model.confs import ConfsModel
from app.model.posts import PostsModel

class BasicCtrl(tornado.web.RequestHandler):
    def initialize(self):
        self._storage = {'model': {}, 'dbase': {}, }
    def on_finish(self):
        for dbase in self._storage['dbase']:
            self._storage['dbase'][dbase].close()

    def set_default_headers(self):
        self.clear_header('server')
        self.set_header('x-frame-options', 'SAMEORIGIN')
        self.set_header('x-xss-protection', '1; mode=block')
        self.set_header('cache-control', 'no-siteapp')

    def head(self, *args, **kwargs):
        apply(self.get, args, kwargs)
    def hello_world(self):
        self.write('Hello world')
    def write_error(self, status_code, **kwargs):
        if not self.settings['error']:
            return self.render('error.html', code = status_code, msgs = self._reason)
        return apply(super(BasicCtrl, self).write_error, [status_code], kwargs)

    def get_runtime_conf(self, name):
        return self.model('confs').get(self.dbase('confs'), name)

    def has_runtime_conf(self, name):
        return self.model('confs').has(self.dbase('confs'), name)

    def del_runtime_conf(self, name):
        return self.model('confs').delete(self.dbase('confs'), name)

    def set_runtime_conf(self, name, vals):
        return self.model('confs').set(self.dbase('confs'), name, vals)

    def get_current_user(self):
        sess = self.get_secure_cookie("_user")
        if (sess):
            sess = self.get_escaper().json_decode(sess)
            if type(sess) == type({}) and 'user_id' in sess and 'auth_word' in sess:
                user = self.model('admin').get_user_by_usid(self.dbase('users'), sess['user_id'])
                if user and self.model('admin').generate_authword(user['user_atms'], user['user_salt']) == sess['auth_word']:
                    return user
            self.del_current_user()
    def del_current_user(self):
        self.clear_cookie("_user")

    def merge_query(self, args, dels = []):
        for k in self.request.arguments.keys():
            if k not in args:
                args[k] = self.get_argument(k)
        for k in dels:
            if k in args:
                del args[k]
        return args

    def get_escaper(self):
        return tornado.escape

    def fetch_xsrfs(self):
        return '_xsrf=' + self.get_escaper().url_escape(self.xsrf_token)

    def human_valid(self):
        if self.get_runtime_conf('rapri'):
            return submit(self.input('recaptcha_challenge_field', None), self.input('recaptcha_response_field', None), \
                    self.get_runtime_conf('rapri'), self.request.remote_ip).is_valid
        else:
            return not bool(self.get_runtime_conf('rapub'))

    def utils(self):
        return Utils

    def cache(self):
        return Cache

    def timer(self):
        return time

    def stime(self):
        return int(time.time())

    def tourl(self, args, base = None):
        if base == None:
            base = self.request.path
        return tornado.httputil.url_concat(base, args)

    def input(self, *args, **kwargs):
        return apply(self.get_argument, args, kwargs)

    def flash(self, stat, exts = {}):
        if stat:
            exts['err'] = 0
        else:
            exts['err'] = 1

        if 'sta' not in exts:
            exts['sta'] = self.get_status()

        if 'msg' not in exts:
            try:
                exts['msg'] = tornado.httputil.responses[exts['sta']]
            except KeyError:
                exts['msg'] = ''

        if 'url' not in exts: exts['url'] = ''
        if 'ext' not in exts: exts['ext'] = {}

        if ('Accept' in self.request.headers) and (self.request.headers['Accept'].find('json') >= 0):
            self.write(self.get_escaper().json_encode(exts))
        else:
            self.render('flash.html', flash = exts)

    def confs(self):
        return self.model('confs')

    def dbase(self, name):
        if name not in self._storage['dbase']:
            self._storage['dbase'][name] = sqlite3.connect(self.settings['dbase'][name])
            self._storage['dbase'][name].row_factory = sqlite3.Row
            self._storage['dbase'][name].text_factory = str
        return self._storage['dbase'][name]

    def model(self, name):
        name = name.title() + 'Model'
        if name not in self._storage['model']:
            self._storage['model'][name] = globals()[name]()
        return self._storage['model'][name]

def alive(method):
    """Decorate methods with this to require that the user be logged in.

    If the user is not logged in, they will be redirected to the configured
    `login url <RequestHandler.get_login_url>`.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self.current_user:
            if ('Accept' in self.request.headers) and (self.request.headers['Accept'].find('json') >= 0):
                self.flash(0, {'url': self.get_login_url(), 'sta': 403})
                return

            if self.request.method in ("GET", "HEAD"):
                url = self.get_login_url()
                if "?" not in url:
                    if urlparse.urlsplit(url).scheme:
                        # if login url is absolute, make next absolute too
                        next_url = self.request.full_url()
                    else:
                        next_url = self.request.uri
                        if next_url.find('/index.py') == 0:
                            next_url = next_url.replace('/index.py', '', 1)

                    url += "?" + urlencode(dict(next=next_url))
                self.redirect(url)
                return
            return self.send_error(403)
        return method(self, *args, **kwargs)
    return wrapper
