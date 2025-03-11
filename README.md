# SMD-Manager

An application for managing SMD components, BOM imports, and device assignments.

## Features

- Management of SMD component inventory
- BOM import in CSV format
- DigiKey API integration for product information
- Device assignment for components
- Analysis of missing parts for device production
- Responsive user interface

## Requirements

- Python 3.8 or higher
- Flask
- SQLAlchemy
- Redis (optional for improved caching)

## Installation

### Option 1: Local Installation

1. Clone repository:
```bash
git clone https://github.com/AnimaI/SMD-Manager.git
cd SMD-Manager
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  
# On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure `.env` file:
```
cp .env.example .env
# Edit .env with your settings
```

5. Start application:
```bash
python3 app.py
```

### Option 2: Docker Compose

1. Clone repository:
```bash
git clone https://github.com/AnimaI/SMD-Manager.git
cd SMD-Manager
```

2. Configure .env file:
```
cp .env.example .env
# Edit .env with your settings
```

3. Start Docker Compose:
```bash
docker-compose up -d
```

### Option 3: Setting up as a systemd service

1. Create a systemd service file:
```bash
sudo nano /etc/systemd/system/smd-manager.service
```

2. Add the following configuration (adjust paths as needed):
```
[Unit]
Description=SMD Manager Service
After=network.target

[Service]
User=youruser
Group=yourgroup
WorkingDirectory=/path/to/SMD-Manager
Environment="PATH=/path/to/SMD-Manager/venv/bin"
EnvironmentFile=/path/to/SMD-Manager/.env
ExecStart=/path/to/SMD-Manager/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Reload systemd, enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable smd-manager
sudo systemctl start smd-manager
```

4. Check service status:
```bash
sudo systemctl status smd-manager
```

5. View logs:
```bash
sudo journalctl -u smd-manager -f
```

## BOM Format

The application supports CSV files with the following format:

```
Device,Device Name v1.0
DigiKey-No,Quantity
311-24.3KCRCT-ND,5
CKN10502-ND,10
...
```

## DigiKey API Connection

The application uses the DigiKey API for product information. To use this:

1. Register for DigiKey API access: https://developer.digikey.com/
2. Obtain Client ID and Client Secret
3. Add the credentials to the `.env` file

## Security Notes

- The application should be operated behind a reverse proxy like Nginx
- In production, `FLASK_DEBUG=False` should be set
- API keys should be set as environment variables

## Support

If you like this project and want to support future work, I would appreciate a donation:

<table style="border-collapse: collapse; border: none; width: 100%;">
  <tr>
    <td align="center" width="40%" style="padding: 50px; border: none;">
      <img src="docs/img/btc_qr.png" alt="Bitcoin QR Code" style="display: block; margin: auto;" width="200"/>
      <p style="text-align: center;"><strong>Bitcoin (BTC):</strong><br>bc1qkz29mjsyn5k4hwezf7gxg4gnleh85k0wnm8htd</p>
    </td>
    <td width="20%" style="border: none;"></td> <!-- Empty column for spacing -->
    <td align="center" width="40%" style="padding: 50px; border: none;">
      <img src="docs/img/btc-lightning_qr.svg" alt="Bitcoin Lightning QR Code" style="display: block; margin: auto;" width="200"/>
      <p style="text-align: center;"><strong>Bitcoin Lightning:</strong><br>
        <a href="https://getalby.com/p/animai" target="_blank" rel="noopener noreferrer">animai@getalby.com</a>
      </p>
    </td>
  </tr>
  <tr>
    <td align="center" width="40%" style="padding: 50px; border: none;">
      <img src="docs/img/bmc_qr.png" alt="Buy Me A Coffee QR Code" style="display: block; margin: auto;" width="200"/>
      <p style="text-align: center;"><strong>Buy Me A Coffee:</strong><br>
        <a href="https://buymeacoffee.com/_animai" target="_blank" rel="noopener noreferrer">buymeacoffee.com/_animai</a>
      </p>
    </td>
    <td width="20%" style="border: none;"></td> <!-- Empty column for spacing -->
    <td align="center" width="40%" style="padding: 50px; border: none;">
      <img src="docs/img/qrcode_ko-fi.png" alt="Ko-fi QR Code" style="display: block; margin: auto;" width="200"/>
      <p style="text-align: center;"><strong>Ko-fi:</strong><br>
        <a href="https://ko-fi.com/akamai" target="_blank" rel="noopener noreferrer">ko-fi.com/akamai</a>
      </p>
    </td>
  </tr>
</table>

## License

This project is licensed under the MIT License - see the LICENSE file for details.
