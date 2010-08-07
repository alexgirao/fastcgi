/* gcc -Wall -s fcgi-spawn.c -o fcgi-spawn
 * indent -npro -kr -i8 -ts8 -sob -l80 -ss -ncs fcgi-spawn.c
 */

#include <sys/types.h>
#include <sys/time.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <sys/socket.h>
#include <sys/un.h>

#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <grp.h>
#include <pwd.h>
#include <getopt.h>

#include <arpa/inet.h>

#define FCGI_LISTENSOCK_FILENO 0

#ifndef UNIX_PATH_MAX
# define UNIX_PATH_MAX 108
#endif

int fcgi_spawn_connection(char *appPath, char *addr, unsigned short port,
			  const char *unixsocket, int child_count, int pid_fd,
			  int nofork, gid_t gid)
{
	int fcgi_fd;
	int socket_type, status;
	struct timeval tv = { 0, 100 * 1000 };

	struct sockaddr_un fcgi_addr_un;
	struct sockaddr_in fcgi_addr_in;
	struct sockaddr *fcgi_addr;

	socklen_t servlen;

	if (child_count < 2) {
		child_count = 5;
	}

	if (child_count > 256) {
		child_count = 256;
	}

	if (unixsocket) {
		memset(&fcgi_addr, 0, sizeof(fcgi_addr));

		fcgi_addr_un.sun_family = AF_UNIX;
		strcpy(fcgi_addr_un.sun_path, unixsocket);

		servlen =
		    ((size_t) (((struct sockaddr_un *)0)->sun_path) +
		     strlen((&fcgi_addr_un)->sun_path));

		socket_type = AF_UNIX;
		fcgi_addr = (struct sockaddr *)&fcgi_addr_un;
	} else {
		fcgi_addr_in.sin_family = AF_INET;
		if (addr != NULL) {
			fcgi_addr_in.sin_addr.s_addr = inet_addr(addr);
		} else {
			fcgi_addr_in.sin_addr.s_addr = htonl(INADDR_ANY);
		}
		fcgi_addr_in.sin_port = htons(port);
		servlen = sizeof(fcgi_addr_in);

		socket_type = AF_INET;
		fcgi_addr = (struct sockaddr *)&fcgi_addr_in;
	}

	if (-1 == (fcgi_fd = socket(socket_type, SOCK_STREAM, 0))) {
		fprintf(stderr, "%s.%d\n", __FILE__, __LINE__);
		return -1;
	}

	if (-1 == connect(fcgi_fd, fcgi_addr, servlen)) {

		pid_t child;
		int val;

		if (unixsocket)
			unlink(unixsocket);

		close(fcgi_fd);

		if (-1 == (fcgi_fd = socket(socket_type, SOCK_STREAM, 0))) {
			fprintf(stderr, "%s.%d\n", __FILE__, __LINE__);
			return -1;
		}

		val = 1;
		if (setsockopt
		    (fcgi_fd, SOL_SOCKET, SO_REUSEADDR, &val,
		     sizeof(val)) < 0) {
			fprintf(stderr, "%s.%d\n", __FILE__, __LINE__);
			return -1;
		}

		if (-1 == bind(fcgi_fd, fcgi_addr, servlen)) {
			fprintf(stderr, "%s.%d: bind failed: %s\n",
				__FILE__, __LINE__, strerror(errno));
			return -1;
		}

		if (-1 == listen(fcgi_fd, 1024)) {
			fprintf(stderr, "%s.%d: fd = -1\n", __FILE__, __LINE__);
			return -1;
		}

		if (!nofork) {
			child = fork();
		} else {
			child = 0;
		}

		switch (child) {
		case 0:{
				char cgi_childs[64];
				char *b;

				int i = 0;

				sprintf(cgi_childs, "PHP_FCGI_CHILDREN=%d",
					child_count);

				if (fcgi_fd != FCGI_LISTENSOCK_FILENO) {
					close(FCGI_LISTENSOCK_FILENO);
					dup2(fcgi_fd, FCGI_LISTENSOCK_FILENO);
					close(fcgi_fd);
				}

				for (i = 3; i < 256; i++) {
					close(i);
				}

				putenv(cgi_childs);

				b = malloc(strlen("exec ") + strlen(appPath) +
					   1);
				strcpy(b, "exec ");
				strcat(b, appPath);

				if (unixsocket && gid != -1) {
					struct stat st;

					if (stat(unixsocket, &st)) {
						fprintf(stderr,
							"%s.%d: stating unix socket '%s' failed: %s\n",
							__FILE__, __LINE__,
							unixsocket,
							strerror(errno));
						return -1;
					}
					if (chown(unixsocket, -1, gid)) {
						fprintf(stderr,
							"%s.%d: failed to set group ownership to unix socket\n",
							__FILE__, __LINE__);
						exit(errno);
					}
					if (chmod
					    (unixsocket,
					     st.st_mode | S_IRGRP | S_IWGRP)) {
						fprintf(stderr,
							"%s.%d: failed to set S_IRGRP and S_IWGRP to unix socket\n",
							__FILE__, __LINE__);
						exit(errno);
					}
				}

				execl("/bin/sh", "sh", "-c", b, (char *)NULL);

				exit(errno);

				break;
			}
		case -1:

			break;
		default:

			select(0, NULL, NULL, NULL, &tv);

			switch (waitpid(child, &status, WNOHANG)) {
			case 0:
				fprintf(stderr,
					"%s.%d: child spawned successfully: PID: %d\n",
					__FILE__, __LINE__, child);

				if (pid_fd != -1) {

					char pidbuf[12];

					snprintf(pidbuf, sizeof(pidbuf) - 1,
						 "%d", child);

					write(pid_fd, pidbuf, strlen(pidbuf));
					close(pid_fd);
					pid_fd = -1;
				}

				break;
			case -1:
				break;
			default:
				if (WIFEXITED(status)) {
					fprintf(stderr,
						"%s.%d: child exited with: %d, %s\n",
						__FILE__, __LINE__,
						WEXITSTATUS(status),
						strerror(WEXITSTATUS(status)));
				} else if (WIFSIGNALED(status)) {
					fprintf(stderr,
						"%s.%d: child signaled: %d\n",
						__FILE__, __LINE__,
						WTERMSIG(status));
				} else {
					fprintf(stderr,
						"%s.%d: child died somehow: %d\n",
						__FILE__, __LINE__, status);
				}
			}

			break;
		}
	} else {
		fprintf(stderr, "%s.%d: socket is already used, can't spawn\n",
			__FILE__, __LINE__);
		return -1;
	}

	close(fcgi_fd);

	return 0;
}

void show_version()
{
	char *b = "spawn-fcgi" "-" "1.4.16" " - spawns fastcgi processes\n";
	write(1, b, strlen(b));
}

void show_help()
{
	char *b =
	    "spawn-fcgi" "-" "1.4.16" " - spawns fastcgi processes\n" "usage:\n"
	    " -f <fcgiapp> filename of the fcgi-application\n"
	    " -a <addr>    bind to ip address\n"
	    " -p <port>    bind to tcp-port\n"
	    " -s <path>    bind to unix-domain socket\n"
	    " -C <childs>  (PHP only) numbers of childs to spawn (default 5)\n"
	    " -P <path>    name of PID-file for spawed process\n"
	    " -n           no fork (for daemontools)\n"
	    " -v           show version\n" " -h           show this help\n"
	    "(root only)\n"
	    " -c <dir>     chroot to directory\n"
	    " -u <user>    change to user-id\n"
	    " -g <group>   change to group-id\n";
	write(1, b, strlen(b));
}

int main(int argc, char **argv)
{
	char *fcgi_app = NULL, *changeroot = NULL, *username = NULL,
	    *groupname = NULL, *unixsocket = NULL, *pid_file = NULL,
	    *addr = NULL;
	unsigned short port = 0;
	int child_count = 5;
	int i_am_root, o;
	int pid_fd = -1;
	int nofork = 0;
	int gid = -1;

	i_am_root = (getuid() == 0);

	while (-1 != (o = getopt(argc, argv, "c:f:g:hna:p:u:vC:s:P:"))) {
		switch (o) {
		case 'f':
			fcgi_app = optarg;
			break;
		case 'a':
			addr = optarg;	/* ip addr */
			break;
		case 'p':
			port = strtol(optarg, NULL, 10);	/* port */
			break;
		case 'C':
			child_count = strtol(optarg, NULL, 10);	/*  */
			break;
		case 's':
			unixsocket = optarg;	/* unix-domain socket */
			break;
		case 'c':
			changeroot = optarg;
			break;
		case 'u':
			username = optarg;
			break;
		case 'g':
			groupname = optarg;
			break;
		case 'n':
			nofork = 1;
			break;
		case 'P':
			pid_file = optarg;	/* PID file */
			break;
		case 'v':
			show_version();
			return 0;
		case 'h':
			show_help();
			return 0;
		default:
			show_help();
			return -1;
		}
	}

	if (fcgi_app == NULL || (port == 0 && unixsocket == NULL)) {
		show_help();
		return -1;
	}

	if (unixsocket && port) {
		fprintf(stderr, "%s.%d: %s\n",
			__FILE__, __LINE__,
			"either a unix domain socket or a tcp-port, but not both\n");

		return -1;
	}

	if (unixsocket && strlen(unixsocket) > UNIX_PATH_MAX - 1) {
		fprintf(stderr, "%s.%d: %s\n",
			__FILE__, __LINE__,
			"path of the unix socket is too long\n");

		return -1;
	}

	/* UID handling */
	if (!i_am_root && (geteuid() == 0 || getegid() == 0)) {
		/* we are setuid-root */

		fprintf(stderr, "%s.%d: %s\n",
			__FILE__, __LINE__,
			"Are you nuts ? Don't apply a SUID bit to this binary\n");

		return -1;
	}

	if (pid_file &&
	    (-1 ==
	     (pid_fd =
	      open(pid_file, O_WRONLY | O_CREAT | O_EXCL | O_TRUNC,
		   S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH)))) {
		struct stat st;
		if (errno != EEXIST) {
			fprintf(stderr,
				"%s.%d: opening pid-file '%s' failed: %s\n",
				__FILE__, __LINE__, pid_file, strerror(errno));

			return -1;
		}

		/* ok, file exists */

		if (0 != stat(pid_file, &st)) {
			fprintf(stderr,
				"%s.%d: stating pid-file '%s' failed: %s\n",
				__FILE__, __LINE__, pid_file, strerror(errno));

			return -1;
		}

		/* is it a regular file ? */

		if (!S_ISREG(st.st_mode)) {
			fprintf(stderr,
				"%s.%d: pid-file exists and isn't regular file: '%s'\n",
				__FILE__, __LINE__, pid_file);

			return -1;
		}

		if (-1 ==
		    (pid_fd =
		     open(pid_file, O_WRONLY | O_CREAT | O_TRUNC,
			  S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH))) {
			fprintf(stderr,
				"%s.%d: opening pid-file '%s' failed: %s\n",
				__FILE__, __LINE__, pid_file, strerror(errno));

			return -1;
		}
	}

	if (i_am_root) {
		struct group *grp = NULL;
		struct passwd *pwd = NULL;

		/* set user and group */

		if (username) {
			if (NULL == (pwd = getpwnam(username))) {
				fprintf(stderr, "%s.%d: %s, %s\n",
					__FILE__, __LINE__,
					"can't find username", username);
				return -1;
			}

			if (pwd->pw_uid == 0) {
				fprintf(stderr, "%s.%d: %s\n",
					__FILE__, __LINE__,
					"I will not set uid to 0\n");
				return -1;
			}
		}

		if (groupname) {
			if (NULL == (grp = getgrnam(groupname))) {
				fprintf(stderr, "%s.%d: %s %s\n",
					__FILE__, __LINE__,
					"can't find groupname", groupname);
				return -1;
			}
			if (grp->gr_gid == 0) {
				fprintf(stderr, "%s.%d: %s\n",
					__FILE__, __LINE__,
					"I will not set gid to 0\n");
				return -1;
			}
		}

		if (changeroot) {
			if (-1 == chroot(changeroot)) {
				fprintf(stderr, "%s.%d: %s %s\n",
					__FILE__, __LINE__,
					"chroot failed: ", strerror(errno));
				return -1;
			}
			if (-1 == chdir("/")) {
				fprintf(stderr, "%s.%d: %s %s\n",
					__FILE__, __LINE__,
					"chdir failed: ", strerror(errno));
				return -1;
			}
		}

		/* drop root privs */
		if (groupname) {
			setgid(grp->gr_gid);
		}
		if (username) {
			if (groupname) {
				initgroups(username, grp->gr_gid);
			}
			setuid(pwd->pw_uid);
		}
		if (grp) {
			gid = grp->gr_gid;
		}
	} else {
		if (username) {
			fprintf(stderr, "%s.%d: %s\n",
				__FILE__, __LINE__,
				"need root privileges to change uid");
			return -1;
		}

		if (groupname) {
			fprintf(stderr, "%s.%d: %s\n",
				__FILE__, __LINE__,
				"need root privileges to change gid");
			return -1;
		}

		if (changeroot) {
			fprintf(stderr, "%s.%d: %s\n",
				__FILE__, __LINE__,
				"need root privileges to change root");
			return -1;
		}
	}

	return fcgi_spawn_connection(fcgi_app, addr, port, unixsocket,
				     child_count, pid_fd, nofork, gid);
}
