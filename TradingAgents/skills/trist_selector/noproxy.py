"""
Import BEFORE akshare. Patches only akshare's requests session to bypass proxy.
Does NOT touch baostock or any other library.

Eastmoney APIs reject proxied connections — akshare must go direct.
"""
import os

# Tell akshare to skip proxy for eastmoney domains
os.environ['NO_PROXY'] = 'eastmoney.com,*.eastmoney.com,push2.eastmoney.com,17.push2.eastmoney.com'

# Remove HTTP_PROXY so akshare's requests session doesn't route through proxy
_proxy_keys = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
_saved = {}
for k in _proxy_keys:
    if k in os.environ:
        _saved[k] = os.environ.pop(k)
