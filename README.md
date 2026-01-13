
# HES (Head End System) - Smart Meter Monitoring SystemA comprehensive smart meter monitoring and management system built with FastAPI. This system manages Data Concentrator Units (DCUs) and smart meters, collects real-time readings, and provides both web UI and REST API interfaces for monitoring and control.## Features### Core Functionality- **DCU Management**: Register, monitor, and manage Data Concentrator Units- **Meter Management**: Install, configure, and monitor smart meters- **Real-time Data Collection**: TCP-based communication with meters and DCUs- **Reading Types**:  - Energy Profile Readings  - Instantaneous Profile Readings  - Regular Task Readings (voltage, current, power, energy)- **Line Management**: Organize meters by electrical lines- **System Tasks**: Automated scheduled readings and data collection### Web Interface- Modern, responsive web UI built with Jinja2 templates- Dashboard with system overview- Meter and DCU management interfaces- Data visualization and reading displays- Batch upload functionality- User authentication and session management### REST API- Complete REST API for system integration- Token-based authentication- Comprehensive endpoints for meters, DCUs, readings, and system management- See [API Documentation](api_endpoints/API_DOCUMENTATION.md) for details### Security- User authentication with role-based access control (RBAC)- Session management (120-minute sessions)- Permission-based authorization- Token-based API authentication## Project Structure
HES/
├── main.py # Application entry point
├── webapp.py # FastAPI application and TCP server
├── config.json # Configuration file (IP, port)
├── database.py # Database utilities
├── init_db.py # Database initialization script
├── dcu_handle.py # DCU connection handler
├── routers/ # Web UI route handlers
│ ├── dashboard.py
│ ├── meter_management.py
│ ├── DCU_management.py
│ ├── login.py
│ └── ...
├── api_endpoints/ # REST API endpoints
│ ├── auth_api.py
│ ├── meters_api.py
│ ├── readings_api.py
│ ├── dcu_api.py
│ └── ...
├── services/ # Core services
│ ├── database.py # Database connection and initialization
│ └── state.py # Application state management
├── utils/ # Utility functions
│ ├── frames.py # Communication frame definitions
│ ├── DCU_functions.py
│ ├── meter_task_functions.py
│ └── ...
├── templates/ # HTML templates
├── static/ # CSS, images, and static assets
└── meter_logs/ # Daily meter communication logs
## Prerequisites- Python 3.7+- SQLite3 (included with Python)## Installation1. **Clone or download the repository**2. **Install dependencies** (create a `requirements.txt` if needed with these packages):   ```bash   pip install fastapi uvicorn jinja2 python-multipart apscheduler   ```3. **Initialize the database**:   ```bash   python init_db.py   ```4. **Configure the system**:   Edit `config.json` to set your TCP server IP and port:   ```json   {       "ip_address": "0.0.0.0",       "port": 7777   }   ```## Configuration### config.json- `ip_address`: IP address for TCP server (default: "0.0.0.0")- `port`: Port for TCP server (default: 7777)### Web Server- Default web server runs on `http://0.0.0.0:8000`- Configured in `main.py`## Usage### Running the Application**Development mode:**```bashpython main.py```The application will start:- Web server on `http://localhost:8000`- TCP server on the configured IP:port (default: 0.0.0.0:7777)### Accessing the Web Interface1. Open your browser and navigate to `http://localhost:8000`2. Login with your credentials (default may need to be set up)3. Access various features through the navigation menu:   - Dashboard   - Meter Management   - DCU Management   - Data Readings   - System Tasks### Using the REST API1. **Authenticate**:   ```bash   curl -X POST http://localhost:8000/api/auth/login \     -H "Content-Type: application/json" \     -d '{"username": "admin", "password": "your_password"}'   ```2. **Use the token** in subsequent requests:   ```bash   curl http://localhost:8000/api/meters/installed \     -H "X-API-Token: YOUR_TOKEN_HERE"   ```See [API Documentation](api_endpoints/API_DOCUMENTATION.md) for complete API reference.## Database SchemaThe system uses SQLite with the following main tables:- `registered_dcus`: Registered DCU information- `unregistered_dcu`: Unregistered DCU connections- `installed_meters`: Installed meter configuration- `registered_meters`: Registered meter information- `energy_profile_readings`: Energy profile data- `instantaneous_profile_readings`: Instantaneous readings- `regular_task_readings`: Regular task readings- `users`: User accounts- `roles`: User roles- `permissions`: System permissions- `role_permissions`: Role-permission mappings- `lines`: Electrical line organization- `tasks`: Scheduled system tasks## TCP Communication ProtocolThe system communicates with meters and DCUs via TCP:- **Default Port**: 7777 (configurable in `config.json`)- **Protocol**: Custom frame-based protocol- **Connection Handling**: Async TCP server handles multiple concurrent connections- **Heartbeat Detection**: Automatic detection of meter and DCU heartbeats- **Logging**: All communications are logged to `meter_logs/` directory## Building as ExecutableThe project includes PyInstaller spec files (`main.spec`, `webapp.spec`) for building standalone executables:```bashpyinstaller main.spec```The executable will be created in the `dist/` directory.## Logging- **Communication Logs**: Stored in `meter_logs/` organized by date (MM_DD format)- **Log Format**: `{timestamp} | from METER: {hex_data}`- **Daily Rotation**: New log files created daily per meter## Features in Detail### Meter Management- Install new meters- Configure meter parameters (CT/VT ratios, addresses, passwords)- Monitor connection status- View meter details and history### DCU Management- Register DCUs- Monitor unregistered DCU connections- Configure DCU parameters- Associate meters with DCUs### Reading Collection- **Energy Profile**: Historical energy consumption data- **Instantaneous Profile**: Real-time electrical parameters- **Regular Task**: Scheduled readings with voltage, current, power, and energy data### User Management- Create and manage user accounts- Role-based permissions- Session management- Activity tracking## Troubleshooting### Database Issues- Ensure `connection.db` exists (run `init_db.py` if needed)- Check file permissions for database directory### Connection Issues- Verify `config.json` has correct IP and port- Check firewall settings for TCP port (default: 7777)- Ensure no other service is using the configured port### Web Interface Issues- Check if web server is running on port 8000- Verify session middleware is configured correctly- Check browser console for JavaScript errors## Development### Adding New Features- Web UI routes: Add to `routers/` directory- API endpoints: Add to `api_endpoints/` directory- Utilities: Add to `utils/` directory- Database changes: Update `services/database.py` `init_db()` function### Testing- Web UI: Access through browser and test manually- API: Use curl, Postman, or similar tools- TCP Communication: Test with meter/DCU simulators## Security Considerations- Change default passwords before production use- Configure proper CORS settings in production- Use HTTPS in production environments- Regularly review user permissions and roles- Keep dependencies updated- Consider using environment variables for sensitive configuration## License[Specify your license here]## SupportFor issues, questions, or contributions, please [specify your contact method or issue tracker].## Version History[Add version history if applicable]
bash
pip install fastapi uvicorn jinja2 python-multipart apscheduler
3. **Initialize the database**:   ```bash   python init_db.py
Configure the system:
Edit config.json to set your TCP server IP and port:
   {       "ip_address": "0.0.0.0",       "port": 7777   }
Configuration
config.json
ip_address: IP address for TCP server (default: "0.0.0.0")
port: Port for TCP server (default: 7777)
Web Server
Default web server runs on http://0.0.0.0:8000
Configured in main.py
Usage
Running the Application
Development mode:
python main.py
The application will start:
Web server on http://localhost:8000
TCP server on the configured IP:port (default: 0.0.0.0:7777)
Accessing the Web Interface
Open your browser and navigate to http://localhost:8000
Login with your credentials (default may need to be set up)
Access various features through the navigation menu:
Dashboard
Meter Management
DCU Management
Data Readings
System Tasks
Using the REST API
Authenticate:
   curl -X POST http://localhost:8000/api/auth/login \     -H "Content-Type: application/json" \     -d '{"username": "admin", "password": "your_password"}'
Use the token in subsequent requests:
   curl http://localhost:8000/api/meters/installed \     -H "X-API-Token: YOUR_TOKEN_HERE"
See API Documentation for complete API reference.
Database Schema
The system uses SQLite with the following main tables:
registered_dcus: Registered DCU information
unregistered_dcu: Unregistered DCU connections
installed_meters: Installed meter configuration
registered_meters: Registered meter information
energy_profile_readings: Energy profile data
instantaneous_profile_readings: Instantaneous readings
regular_task_readings: Regular task readings
users: User accounts
roles: User roles
permissions: System permissions
role_permissions: Role-permission mappings
lines: Electrical line organization
tasks: Scheduled system tasks
TCP Communication Protocol
The system communicates with meters and DCUs via TCP:
Default Port: 7777 (configurable in config.json)
Protocol: Custom frame-based protocol
Connection Handling: Async TCP server handles multiple concurrent connections
Heartbeat Detection: Automatic detection of meter and DCU heartbeats
Logging: All communications are logged to meter_logs/ directory
Building as Executable
The project includes PyInstaller spec files (main.spec, webapp.spec) for building standalone executables:
pyinstaller main.spec
The executable will be created in the dist/ directory.
Logging
Communication Logs: Stored in meter_logs/ organized by date (MM_DD format)
Log Format: {timestamp} | from METER: {hex_data}
Daily Rotation: New log files created daily per meter
Features in Detail
Meter Management
Install new meters
Configure meter parameters (CT/VT ratios, addresses, passwords)
Monitor connection status
View meter details and history
DCU Management
Register DCUs
Monitor unregistered DCU connections
Configure DCU parameters
Associate meters with DCUs
Reading Collection
Energy Profile: Historical energy consumption data
Instantaneous Profile: Real-time electrical parameters
Regular Task: Scheduled readings with voltage, current, power, and energy data
User Management
Create and manage user accounts
Role-based permissions
Session management
Activity tracking
Troubleshooting
Database Issues
Ensure connection.db exists (run init_db.py if needed)
Check file permissions for database directory
Connection Issues
Verify config.json has correct IP and port
Check firewall settings for TCP port (default: 7777)
Ensure no other service is using the configured port
Web Interface Issues
Check if web server is running on port 8000
Verify session middleware is configured correctly
Check browser console for JavaScript errors
Development
Adding New Features
Web UI routes: Add to routers/ directory
API endpoints: Add to api_endpoints/ directory
Utilities: Add to utils/ directory
Database changes: Update services/database.py init_db() function
Testing
Web UI: Access through browser and test manually
API: Use curl, Postman, or similar tools
TCP Communication: Test with meter/DCU simulators
