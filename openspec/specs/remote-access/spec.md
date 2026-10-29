# remote-access Specification

## Purpose
TBD - created by archiving change add-digital-twin-phase1. Update Purpose after archive.
## Requirements
### Requirement: share.sh commands
`./share.sh` SHALL provide three commands, `start`, `status` and `stop`, for sharing the dashboard with people on other machines through a Microsoft Dev Tunnel:
- **`start`** creates a tunnel labelled `twin-dashboard` and hosts it in the background with `devtunnel host`, detached from the terminal. It then prints the URL to open from another machine. If a host from an earlier `start` is still running, `start` prints that tunnel's URL and creates nothing. If an earlier host has died, `start` first deletes the tunnel it left behind.
- **`status`** shows whether sharing is on. If it is, it shows the URL, the tunnel ID, the host process, the tunnel's ports, the access rules and the results of the checks through the tunnel.
- **`stop`** stops the host process and deletes the tunnel, so the URL no longer reaches the dashboard.

Any other command SHALL print usage and exit 2. `share.sh` SHALL keep its state in `.share/`, which is git-ignored:
- the tunnel ID
- the URL
- the host process ID
- the host log

`status` and `stop` SHALL also list twin tunnels in the account that the state does not know about, with the command to delete them.

#### Scenario: Start sharing
- **WHEN** the stack is running, the host is logged in to devtunnel, and the user runs `./share.sh start`
- **THEN** a tunnel hosting port 8080 is running in the background
- **AND** the script prints the `https://…devtunnels.ms` URL to open from another machine, who can sign in, when access expires and the check results, and exits 0

#### Scenario: Status while sharing
- **WHEN** sharing is on and the user runs `./share.sh status`
- **THEN** it prints that sharing is on, with the URL, the tunnel ID, the ports, the access rules and the check results

#### Scenario: Status while not sharing
- **WHEN** sharing is off and the user runs `./share.sh status`
- **THEN** it prints that sharing is off and exits 0

#### Scenario: Host died
- **WHEN** the host process has stopped, for example after a reboot, but its tunnel still exists, and the user runs `./share.sh status`
- **THEN** it reports that sharing is off and the tunnel is left over, shows the end of the host log, and exits 1
- **AND** a following `./share.sh stop` or `./share.sh start` deletes the left-over tunnel

#### Scenario: Stop sharing
- **WHEN** sharing is on and the user runs `./share.sh stop`
- **THEN** the host process stops, the tunnel is deleted, `.share/` is removed, and the old URL no longer reaches the dashboard

#### Scenario: Stop is idempotent
- **WHEN** sharing is off and the user runs `./share.sh stop`
- **THEN** it reports that nothing is shared and exits 0

#### Scenario: Start twice
- **WHEN** sharing is on and the user runs `./share.sh start` again
- **THEN** it prints the existing URL and does not create a second tunnel

#### Scenario: Stop without a valid login
- **WHEN** the devtunnel login has expired and the user runs `./share.sh stop`
- **THEN** the host process stops, so the URL no longer reaches the dashboard
- **AND** the script keeps the tunnel ID in `.share/`, prints that the tunnel could not be deleted with `devtunnel user login -g` as the fix, and exits 1

### Requirement: Only the dashboard is exposed
The tunnel SHALL host exactly one port, 8080, the dashboard. `start` SHALL read the tunnel's port list before hosting, and stop with an error if it holds any other port.

`share.sh` SHALL NOT expose any of these, directly or as extra tunnel ports:
- MQTT (1883)
- RTSP (8554)
- HLS (8888)
- the serial bridges (7001 and 7002)
- ground truth (9100)
- the trial control port (9200)

Remote viewers SHALL reach the world only through the dashboard: its fault buttons, scenario runner and trial pad.

#### Scenario: Tunnel ports
- **WHEN** sharing is on and `devtunnel port list <tunnel-id>` is run
- **THEN** it lists port 8080 and no other port

#### Scenario: Other ports not reachable remotely
- **WHEN** a remote viewer asks for another port, such as 9200, 1883 or 8554, through the tunnel's host name
- **THEN** no connection to that service is made

### Requirement: Access requires sign-in
The tunnel SHALL never allow anonymous access. A viewer SHALL sign in with a Microsoft or GitHub account that the tunnel's access rules allow. This protection is required because the dashboard can inject faults and move workers, and it controls Docker on the host.

The tunnel is therefore never public, so no basic-auth password is added; the tunnel service enforces sign-in.

By default, `start` SHALL grant access only to the tunnel owner. (A default rule for this clone's `origin` repository was planned, but `devtunnel` 1.0.1972 and 1.0.2115 reject every repository rule with "Specify access control parameters" before contacting the service.)

These options SHALL change who has access, explicitly:
- `--repo <owner/repo>` adds accounts with access to that GitHub repository. If `devtunnel` rejects the rule, `start` SHALL delete the tunnel, exit non-zero and say how to share without it.
- `--org <github-org>`, which can be repeated, adds members of a GitHub organization.
- `--tenant` adds the owner's Entra tenant.
- `--owner-only` grants no one but the owner, and cannot be combined with the other options.

`--expires <1h…30d>` SHALL make the access rules and the tunnel expire after that time. Without it they last until `stop`.

`start` SHALL refuse `--allow-anonymous`, `-a` and `--anonymous`. It SHALL also check that the tunnel has no rule allowing anonymous access before hosting it. After hosting, it SHALL send an anonymous request through the tunnel. If that request reaches the dashboard, `start` SHALL stop the host, delete the tunnel and exit non-zero.

#### Scenario: Anonymous visitor
- **WHEN** someone who is not signed in opens the shared URL
- **THEN** they are sent to the Dev Tunnels sign-in page and do not reach the dashboard

#### Scenario: Allowed viewer
- **WHEN** a viewer signs in with an account the access rules allow (by default, the tunnel owner's)
- **THEN** the dashboard loads

#### Scenario: Anonymous refused
- **WHEN** the user runs `./share.sh start --allow-anonymous`
- **THEN** the script refuses with an explanation, exits non-zero and creates no tunnel

#### Scenario: Open tunnel taken down
- **WHEN** the anonymous request made by `start` reaches the dashboard
- **THEN** `start` stops hosting, deletes the tunnel, prints why and exits non-zero

### Requirement: Remote video and live view
Through the tunnel, the dashboard SHALL work fully:
- the live 3D view over the `/live` WebSocket (`wss:` on the tunnel's https origin)
- the camera video, played as the dashboard's same-origin HLS stream under `/video/` (not raw RTSP)
- the scenario, weather, product, fault and trial controls

`start` and `status` SHALL check this through the tunnel as a signed-in client, using a short-lived connect token for the tunnel. The token is sent in a request header and never printed or passed on a command line. The check passes when the dashboard page and the video playlist both load.

#### Scenario: Video plays remotely
- **WHEN** a signed-in remote viewer opens the shared URL
- **THEN** the camera video plays in their browser and the 3D view updates live

#### Scenario: Remote trial walk-in
- **WHEN** a signed-in remote viewer walks the worker into the zone with the trial pad
- **THEN** they see caution, then warning, then alarm, then reset, and the worker stops if their connection drops

### Requirement: Preconditions and clear errors
`start` SHALL check these before creating a tunnel:
- that the dashboard answers on `http://127.0.0.1:8080`
- that `devtunnel` is installed
- that the user is logged in to devtunnel

If a check fails, `start` SHALL print the fix, such as `docker compose up -d --build`, the devtunnel install command or `devtunnel user login -g`, and exit non-zero.

`start` and `status` SHALL warn if the dashboard also listens on an address other than loopback, because people on that network could then use it without signing in.

#### Scenario: Not logged in
- **WHEN** the devtunnel login has expired and the user runs `./share.sh start`
- **THEN** the script prints `devtunnel user login -g` as the fix, exits non-zero and creates no tunnel

#### Scenario: Dashboard not running
- **WHEN** nothing answers on port 8080 and the user runs `./share.sh start`
- **THEN** the script prints `docker compose up -d --build` as the fix and exits non-zero

### Requirement: Documented setup and teardown
The README SHALL document remote access:
- one-time setup: installing devtunnel and running `devtunnel user login -g`
- starting, checking and stopping sharing
- who can sign in, and how to widen or limit access
- that the dashboard is bound to localhost, and why
- teardown, including finding leftover tunnels with `devtunnel list --labels twin-dashboard` and deleting them with `devtunnel delete`

#### Scenario: README covers teardown
- **WHEN** a reader follows the README's remote access teardown steps
- **THEN** no tunnel for the twin remains in `devtunnel list`

