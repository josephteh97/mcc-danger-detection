## ADDED Requirements

### Requirement: share.sh commands
`./share.sh` SHALL provide three commands, `start`, `status` and `stop`, for sharing the dashboard with people on other machines through a Microsoft Dev Tunnel:
- **`start`** creates or reuses the tunnel and starts hosting it in the background. It then prints the URL to open from another machine.
- **`status`** shows whether sharing is on, and if so the URL, the tunnel ID and the access rules.
- **`stop`** stops hosting and deletes the tunnel, so the URL no longer works.

Any other command SHALL print usage and exit non-zero. `share.sh` SHALL keep its state (tunnel ID, host process ID, URL and log) in `.share/`, which is git-ignored.

#### Scenario: Start sharing
- **WHEN** the stack is running and the host is logged in to devtunnel, and the user runs `./share.sh start`
- **THEN** a tunnel hosting port 8080 is running in the background
- **AND** the script prints the `https://…devtunnels.ms` URL to open from another machine, and exits 0

#### Scenario: Status while sharing
- **WHEN** sharing is on and the user runs `./share.sh status`
- **THEN** it prints that sharing is on, with the URL, the tunnel ID and the access rules

#### Scenario: Status while not sharing
- **WHEN** sharing is off and the user runs `./share.sh status`
- **THEN** it prints that sharing is off and exits 0

#### Scenario: Stop sharing
- **WHEN** sharing is on and the user runs `./share.sh stop`
- **THEN** the host process stops, the tunnel is deleted, `.share/` is cleared, and the old URL no longer reaches the dashboard

#### Scenario: Stop is idempotent
- **WHEN** sharing is off and the user runs `./share.sh stop`
- **THEN** it reports that nothing was shared and exits 0

#### Scenario: Start twice
- **WHEN** sharing is on and the user runs `./share.sh start` again
- **THEN** it prints the existing URL and does not create a second tunnel

### Requirement: Only the dashboard is exposed
The tunnel SHALL host exactly one port, 8080, the dashboard.

`share.sh` SHALL NOT expose any of these, directly or as extra tunnel ports:
- MQTT (1883)
- RTSP (8554)
- HLS (8888)
- the serial bridges (7001 and 7002)
- ground truth (9100)
- the trial control port (9200)

Remote viewers SHALL reach the world only through the dashboard: its fault buttons, scenario runner and trial pad.

#### Scenario: Tunnel ports
- **WHEN** sharing is on and `devtunnel show <tunnel-id>` is run
- **THEN** it lists port 8080 and no other port

#### Scenario: Control port not reachable remotely
- **WHEN** a remote viewer tries to reach port 9200, 1883 or 8554 through the tunnel host name
- **THEN** no connection is made

### Requirement: Access requires sign-in
The tunnel SHALL never allow anonymous access. A viewer SHALL sign in with a Microsoft or GitHub account that the tunnel's access rules allow. This protection is required because the dashboard can inject faults and move workers, and it controls Docker on the host.

By default, `start` SHALL grant access only to:
- the tunnel owner
- accounts with access to the GitHub repository `josephteh97/mcc-danger-detection`

Optional flags SHALL widen access explicitly:
- `--org <github-org>` for members of a GitHub organization
- `--tenant` for the owner's Entra tenant

Optional `--expires <1h…30d>` SHALL limit how long the access grant lasts. `start` SHALL refuse any option that would allow anonymous access.

#### Scenario: Anonymous visitor
- **WHEN** someone not signed in opens the shared URL
- **THEN** they are sent to the Dev Tunnels sign-in page and do not reach the dashboard

#### Scenario: Allowed viewer
- **WHEN** a viewer signs in with a GitHub account that has access to the repository
- **THEN** the dashboard loads

#### Scenario: Anonymous refused
- **WHEN** the user runs `./share.sh start --allow-anonymous`
- **THEN** the script refuses with an explanation and creates no tunnel

### Requirement: Remote video and live view
Through the tunnel, the dashboard SHALL work fully:
- the live 3D view over the `/live` WebSocket
- the camera video, played as the dashboard's same-origin HLS stream under `/video/` (not raw RTSP)
- the scenario, weather, product, fault and trial controls

#### Scenario: Video plays remotely
- **WHEN** a signed-in remote viewer opens the shared URL
- **THEN** the camera video plays in their browser and the 3D view updates live

#### Scenario: Remote trial walk-in
- **WHEN** a signed-in remote viewer walks the worker into the zone with the trial pad
- **THEN** they see caution, then warning, then alarm, then reset, and the worker stops if their connection drops

### Requirement: Preconditions and clear errors
`start` SHALL check before creating a tunnel:
- that `devtunnel` is installed and the user is logged in
- that the dashboard answers on `http://127.0.0.1:8080`

If a check fails, it SHALL print the fix, for example `devtunnel user login -g` or `docker compose up -d --build`, and exit non-zero.

#### Scenario: Not logged in
- **WHEN** the devtunnel login has expired and the user runs `./share.sh start`
- **THEN** the script prints `devtunnel user login -g` as the fix, exits non-zero and creates no tunnel

#### Scenario: Dashboard not running
- **WHEN** nothing answers on port 8080 and the user runs `./share.sh start`
- **THEN** the script prints `docker compose up -d --build` as the fix and exits non-zero

### Requirement: Documented setup and teardown
The README SHALL document remote access:
- one-time setup: installing devtunnel and `devtunnel user login -g`
- starting, checking and stopping sharing
- who can sign in, and how to widen or limit access
- that the dashboard is bound to localhost and why
- teardown, including deleting any leftover tunnels with `devtunnel list` and `devtunnel delete`

#### Scenario: README covers teardown
- **WHEN** a reader follows the README's remote access teardown steps
- **THEN** no tunnel for the twin remains in `devtunnel list`
