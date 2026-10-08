# VPN sidecar: OpenVPN client + HTTP proxy, one container per site.
#
# The tunnel lives here and NOT on the VPS host, so a pushed default route can
# never take the server off the internet. Worst case this container breaks
# while SSH, the website, the WhatsApp bridges and the agents keep running.
FROM debian:stable-slim

# socat carries the non-HTTP protocols an HTTP proxy cannot: the hotel's IDS Next
# PMS is a SQL Server application, so its data arrives over TCP/1433, not HTTP.
RUN apt-get update && apt-get install -y --no-install-recommends \
        openvpn tinyproxy socat iproute2 iputils-ping curl ca-certificates nmap \
    && rm -rf /var/lib/apt/lists/*

COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8888
HEALTHCHECK --interval=60s --timeout=5s --start-period=45s --retries=3 \
  CMD test -d /sys/class/net/tun0 || exit 1

ENTRYPOINT ["/entrypoint.sh"]
