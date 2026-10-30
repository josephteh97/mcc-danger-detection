## MODIFIED Requirements

### Requirement: share.sh commands
`./share.sh` SHALL provide three commands, `start`, `status` and `stop`, for sharing the dashboard with people on other machines through a Microsoft Dev Tunnel:
- **`start`** creates a tunnel labelled `twin-dashboard` and hosts it in the background with `devtunnel host`, detached from the terminal. It then prints the URL to open from another machine. If a host from an earlier `start` is still running, `start` prints that tunnel's URL, creates nothing, and runs the anonymous-access check on the running tunnel again; if that check gets through, it stops sharing and exits non-zero. Options such as `--repo`, `--org`, `--tenant`, `--owner-only` and `--expires` apply only when a new tunnel is created, so while sharing is on, `start` with any option SHALL be refused with a message to run `stop` first. If an earlier host has died, `start` first deletes the tunnel it left behind.
- **`status`** shows whether sharing is on. If it is, it shows the URL, the tunnel ID, the host process, the tunnel's ports, the access rules and the results of the checks through the tunnel.
- **`stop`** stops the host process and deletes the tunnel, so the URL no longer reaches the dashboard.

Only one `start` or `stop` SHALL run at a time: a second one started meanwhile SHALL exit non-zero with "another ./share.sh start or stop is running". The lock is held on the script file itself, so it adds no state, and the tunnel host does not inherit it.

If `start` fails after it has chosen a tunnel ID, it SHALL stop any host it started and delete the tunnel before exiting, so a failed start leaves no tunnel behind. The tunnel ID SHALL be written to `.share/` before the tunnel is created, so this clean-up always knows what to delete.

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
- **THEN** it prints the existing URL, repeats the sign-in check and does not create a second tunnel

#### Scenario: Options while sharing
- **WHEN** sharing is on and the user runs `./share.sh start --expires 2d` or `./share.sh start --org my-org`
- **THEN** it refuses, says the options would not apply and to run `./share.sh stop` first, exits non-zero, and leaves the running tunnel unchanged

#### Scenario: Two starts at once
- **WHEN** `./share.sh start` is run while another `start` or `stop` is still running
- **THEN** the second one exits non-zero with "another ./share.sh start or stop is running" and changes nothing

#### Scenario: Failed start cleans up
- **WHEN** `start` fails after creating the tunnel, for example because the access rule is rejected or the anonymous check gets through
- **THEN** the host is stopped, the tunnel is deleted, and `devtunnel list --labels twin-dashboard` shows no tunnel from that run

#### Scenario: Stop without a valid login
- **WHEN** the devtunnel login has expired and the user runs `./share.sh stop`
- **THEN** the host process stops, so the URL no longer reaches the dashboard
- **AND** the script keeps the tunnel ID in `.share/`, prints that the tunnel could not be deleted with `devtunnel user login -g` as the fix, and exits 1

## ADDED Requirements

### Requirement: Engineer access through Tailscale
In the `v11` profile, maintenance engineers SHALL reach any device on `poe_lan` through a Tailscale node on the 4G router (subnet route `192.168.10.0/24`), emulated as a container on `wan_4g` and `poe_lan`. Only engineers in the tailnet's access list SHALL be allowed. This is separate from `share.sh`, which shares the twin's own dashboard.

#### Scenario: Engineer reaches the AI box
- **WHEN** an emulated engineer client in the tailnet opens SSH to the AI box at its `poe_lan` address
- **THEN** the connection succeeds through the router's Tailscale node

### Requirement: Superior view through the cloud relay
In the `v11` profile, the superior SHALL see alarms, events and live view on a cloud relay that the AI box connects out to. The superior's path SHALL never reach `poe_lan` directly.

#### Scenario: Superior cannot reach the LAN
- **WHEN** the emulated superior client tries to connect to any `poe_lan` address
- **THEN** the connection fails, and the cloud relay still shows the latest events and the live view

### Requirement: No inbound port on 4G
The pole SHALL have no inbound port open on the 4G side (carrier-grade NAT). Both remote paths SHALL be outbound connections from the pole.

#### Scenario: Port scan from the 4G side
- **WHEN** a client on `wan_4g` outside the tailnet scans the router's 4G address
- **THEN** no port answers

### Requirement: Remote access survives an AI box or switch fault
The router's Tailscale node SHALL stay reachable while the AI box or the PoE switch has hung, because the router has its own PoE injector, so an engineer can trigger the router-driven switch restart remotely.

#### Scenario: Remote restart during a switch hang
- **WHEN** the switch-hang fault is injected and an engineer connects through the tailnet
- **THEN** the engineer reaches the router, triggers the switch restart, and the camera stream and arm link return within 60 s
