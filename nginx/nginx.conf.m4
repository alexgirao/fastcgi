error_log  pwd/logs/error.log;

worker_processes  5;
pid        pwd/logs/nginx.pid;
worker_rlimit_nofile 8192;

events {
    worker_connections  4096;
}

http {
    include    pwd/mime.types;
    include    pwd/proxy.conf;
    include    pwd/fastcgi.conf;

    client_body_temp_path pwd/logs/client_body_temp;

    default_type application/octet-stream;
    log_format   main '$remote_addr - $remote_user [$time_local] $status '
                      '"$request" $body_bytes_sent "$http_referer" '
                      '"$http_user_agent" "$http_x_forwarded_for"';
    access_log   pwd/logs/access.log  main;
    sendfile     on;
    tcp_nopush   on;
    server_names_hash_bucket_size 128; # this seems to be required for some vhosts

    server { # php/fastcgi
        listen       8020;
        server_name  domain1.com www.domain1.com;
        access_log   pwd/logs/domain1.access.log  main;
        root         pwd/html;

#         location / {
#             index    index.html index.htm index.php;
#         }

        location / {
#             fastcgi_pass 127.0.0.1:8030;
            fastcgi_pass unix:pwd/../fcgi.socket;
        }
    }
}
