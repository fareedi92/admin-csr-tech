# CSR Dashboard Widget Flask App

A Flask application that integrates and runs the CSR Dashboard widget on port 5002.

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements_widget.txt
```

### 2. Run the Application

```bash
python csr_widget_app.py
```

The app will be available at: `http://localhost:5002`

### 3. Features

- ✅ CSR Dashboard widget integrated
- ✅ CORS enabled for cross-origin requests
- ✅ Health check endpoint at `/health`
- ✅ Professional UI with sidebar dashboard
- ✅ Real-time widget integration
- ✅ Connection to backend server at `http://52.74.227.205:5003`

## File Structure

```
/home/ubuntu/
├── csr_widget_app.py          # Flask application
├── requirements_widget.txt    # Python dependencies
└── templates/
    └── csr_dashboard.html     # CSR Dashboard widget template
```

## Configuration

The widget configuration can be modified in `templates/csr_dashboard.html`:

```html
<script
    src="http://52.74.227.205:5003/static/js/csr-dashboard-widget.js"
    data-base-url="http://52.74.227.205:5003"
    data-csr-key="csr_aridian_52_74_227_205_demo"
    data-container-id="csr-console">
</script>
```

## Troubleshooting

- **Port already in use**: Change the port in `csr_widget_app.py` (line 24)
- **Widget not loading**: Check that `http://52.74.227.205:5003` is accessible
- **CORS issues**: Review the CORS configuration in `csr_widget_app.py`

## Endpoints

- `GET /` - Main dashboard page with widget
- `GET /health` - Health check endpoint
