# padherder_proxy
MITM proxy to intercept Puzzles and Dragons box data and sync with padherder.com

# Requires
Python 2.7

mitmproxy (pip install mitmproxy)

requests (pip install requests)

dnslib (pip install dnslib)


# Usage
For now, you need to create a file named "padherder_proxy_settings.txt" with your padherder username as the first
line of the file and your padherder password as the second line

Then you should be able to do:
python padherder_proxy.py

Then on your iOS device, set your HTTP proxy to be your computer's ip address. Then go to Safari and go to "http://mitm.it", click the iOS link and click install to install the certificate. You only have to do this once, and once it is done, you can remove the HTTP proxy settings

Then every time you want to sync, change your DNS settings to point to your computer's ip address. Then close PAD completely and open it. After you get in game, close PAD completely and change your DNS settings back. Your padherder should now be synced to your box.
