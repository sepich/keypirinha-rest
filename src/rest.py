# Keypirinha: a fast launcher for Windows (keypirinha.com)

import keypirinha as kp
import keypirinha_util as kpu
import ctypes, os, time, ssl, traceback
import urllib.request as url
import json
import re

class Rest(kp.Plugin):
  """
  List hosts from CMDB

  Reads some REST API endpoint, configured in config. Pulls out json array,
  for each element creates Catalog item from congured properties.
  Action which is executed for those Items is also configured.
  """
  REGEX_PLACEHOLDER = re.compile(r"\{\{(q?args|q?\*|q?\d+)\}\}", re.ASCII)
  ITEMCAT_HOST = 10 #kp.ItemCategory.USER_BASE + 1

  skip_cert_check = False
  hit_hint = kp.ItemHitHint.NOARGS
  args_hint = kp.ItemArgsHint.FORBIDDEN
  uri=None
  ico_host = None
  ico_type = None
  cmd = None

  def __init__(self):
    super().__init__() # good pratice
    self._debug = True # enables self.dbg() output

  def on_start(self):
    self.dbg("On Start")
    self._read_config()
    self.ico_host = self.load_icon(r'@%windir%\system32\newdev.exe,0')
    # self.ico_host = self.load_icon('@%windir%\system32\wmploc.dll,113')
    # self.ico_type = self.load_icon("@%windir%\system32\wmploc.dll,116")

  def on_catalog(self):
    self.dbg("On Catalog")
    start = time.perf_counter()
    catalog = []

    data = self._read_db()
    # hosts
    if data:
      for entry in data:
        catalog.append(self.create_item(
          category=self.ITEMCAT_HOST,
          label=entry['serverName'],
          short_desc=', '.join(entry['types']) if entry['types'] else 'None',
          target=entry['serverName'],
          args_hint=self.args_hint,
          hit_hint=self.hit_hint,
          icon_handle=self.ico_host))

    # types
    # types = {}
    # for entry in data:
    #   if entry['types']:
    #     for type in entry['types']:
    #       if type in types:
    #         types[type]+=1
    #       else:
    #         types[type]=1
    # for type in types:
    #   catalog.append(self.create_item(
    #     category=kp.ItemCategory.KEYWORD,
    #     label=type,
    #     short_desc='Hosts: {}'.format(types[type]),
    #     target=type,
    #     args_hint=kp.ItemArgsHint.ACCEPTED,
    #     hit_hint=self.hit_hint,
    #     icon_handle=self.ico_type))

    self.set_catalog(catalog)
    elapsed = time.perf_counter() - start
    self.info("Cataloged {} item{} in {:.1f} seconds".format(len(catalog), "s"[len(catalog)==1:], elapsed))

  def on_suggest(self, user_input, items_chain):
    self.dbg( 'On Suggest "{}" (items_chain[{}])'.format(user_input, len(items_chain)) )
    # if items_chain: self.dbg(items_chain[-1].category())
    if items_chain and items_chain[-1].category() == self.ITEMCAT_HOST:
      clone = items_chain[-1].clone()
      clone.set_args(user_input)
      self.set_suggestions([clone])

  def on_execute(self, item, action):
    # self.dbg(item.category())
    # self.dbg(self.ITEMCAT_HOST)
    if item.category() == self.ITEMCAT_HOST:
      msg = 'On Execute "{}" (action: {})'.format(item, action)
      self.dbg(msg)
      self.dbg(item.raw_args())
      cmd = self._customcmd_apply_args(self.cmd, item.label(), item.raw_args())
      self.dbg(cmd)
      try:
        args = kpu.cmdline_split(cmd)
        kpu.shell_execute(args[0], args=args[1:])
      except:
        traceback.print_exc()
    else:
      kpu.execute_default_action(self, item, action)

  def on_activated(self):
    self.dbg("On App Activated")

  def on_deactivated(self):
    self.dbg("On App Deactivated")

  def on_events(self, flags):
    self.dbg("On event(s) (flags {:#x})".format(flags))
    if flags & kp.Events.PACKCONFIG:
      self._read_config()

  # read ini config
  def _read_config(self):
    settings = self.load_settings()
    keep_history = settings.get_bool("keep_history", "main", True)
    self.hit_hint = kp.ItemHitHint.NOARGS if keep_history else kp.ItemHitHint.IGNORE
    self.skip_cert_check = settings.get_bool("skip_cert_check", "main", False)
    self.uri = settings.get("uri", "main", unquote=True)
    self.cmd = settings.get("cmd", "main")
    if not self.cmd or self.REGEX_PLACEHOLDER.search(self.cmd) is None:
      self.args_hint = kp.ItemArgsHint.FORBIDDEN
    else:
      self.args_hint = kp.ItemArgsHint.ACCEPTED

  # load uri or fallback to cache
  def _read_db(self):
    cache_dir = kp.package_cache_dir(self.full_name())
    cache_file = cache_dir+"\cache.json"
    data = None

    ctx = ssl.create_default_context()
    if self.skip_cert_check:
      ctx.check_hostname = False
      ctx.verify_mode = ssl.CERT_NONE

    try:
      os.makedirs(cache_dir, exist_ok=True)
      r=url.urlopen(self.uri, context=ctx)
      if self.should_terminate():
        return []
      if r.getcode()==200:
        data=json.load(r)
        with open(cache_file, 'w') as f:
          json.dump(data, f)
    except Exception as e:
      self.warn("Unable to load uri: '{}' Error: {}".format(self.uri, e))

    if not data and os.path.exists(cache_file):
      with open(cache_file, 'r') as f:
        data = json.load(f)

    return data

  # insert args to placeholders
  def _customcmd_apply_args(self, cmdline, item, args_str):
    try:
      args = kpu.cmdline_split(args_str)
    except:
      traceback.print_exc()
      return cmd_lines

    arg0 = item
    start_pos = 0
    while True:
        rem = self.REGEX_PLACEHOLDER.search(cmdline, start_pos)
        if not rem:
            break

        placeholder = rem.group(1)
        if placeholder in ("*", "args"):
            args_str = args_str.strip()
            cmdline = cmdline[0:rem.start()] + args_str + cmdline[rem.end():]
            start_pos = rem.start() + len(args_str)
        elif placeholder in ("q*", "qargs"):
            if not len(args):
                cmdline = cmdline[0:rem.start()] + "" + cmdline[rem.end():]
                start_pos = rem.start()
            else:
                quoted_args = kpu.cmdline_quote(args, force_quote=True)
                cmdline = cmdline[0:rem.start()] + quoted_args + cmdline[rem.end():]
                start_pos = rem.start() + len(quoted_args)
        else:
            force_quote = False
            if placeholder[0] == "q":
                force_quote = True
                placeholder = placeholder[1:]

            arg_idx = int(placeholder)
            if arg_idx == 0:
                quoted_arg = kpu.cmdline_quote(arg0, force_quote=force_quote)
            else:
                arg_idx = arg_idx - 1
                quoted_arg = kpu.cmdline_quote(
                    args[arg_idx] if arg_idx < len(args) else "",
                    force_quote=force_quote)

            cmdline = cmdline[0:rem.start()] + quoted_arg + cmdline[rem.end():]
            start_pos = rem.start() + len(quoted_arg)

    return cmdline