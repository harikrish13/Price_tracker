# Price Comparison Tool

A modern web application that compares product prices across major retailers (Amazon, Walmart, and Target) to help users find the best deals and track price changes.

## Features

- **Multi-Store Price Comparison**: Searches across Amazon, Walmart, and Target simultaneously
- **Real-Time Price Updates**: Gets current prices directly from retailer websites
- **Price History Visualization**: View price trends over time with interactive charts
- **Sorted Results**: Displays all products sorted from lowest to highest price
- **Detailed Product Information**:
  - Product title and description
  - Current price
  - High-quality product images
  - Ratings and review counts
  - Direct links to product pages
- **Modern User Interface**:
  - Clean, responsive design
  - Material Design-inspired components
  - Loading indicators and animations
  - Mobile-friendly layout
  - Interactive price history charts

## Prerequisites

- Python 3.8 or higher
- Chrome browser (latest version recommended)
- pip (Python package installer)

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd price-tracker
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

## Configuration

The application uses Chrome WebDriver for web scraping. The WebDriver will be automatically downloaded and configured when you run the application.

## Running the Application

1. Start the backend server:
```bash
python app.py
```
The server will start on `http://localhost:8000`

2. Open `index.html` in your web browser to access the user interface.

## Usage

1. Enter a product name in the search bar
2. Click the "Search" button or press Enter
3. Wait for the results to load (this may take a few moments)
4. View the results sorted by price
5. For each product you can:
   - Click "View Deal" to go to the retailer's website
   - Click "Price History" to view price trends
   - Compare prices across different retailers

## Technical Details

### Backend
- FastAPI (Python) for the REST API
- SQLAlchemy for database management
- Selenium with undetected-chromedriver for web scraping
- APScheduler for background tasks

### Frontend
- Modern HTML5 and CSS3
- Vanilla JavaScript for interactivity
- Chart.js for price history visualization
- Responsive design with CSS Grid and Flexbox
- Material Design-inspired components

## Performance Optimizations

- Efficient web scraping with retry mechanisms
- Parallel processing of multiple retailers
- Caching of frequently accessed data
- Optimized image loading and rendering
- Debounced search functionality

## Known Limitations

- Search results may take 15-30 seconds due to anti-bot measures
- Some retailers may occasionally block automated access
- Product availability and prices are subject to change
- Image loading may vary depending on retailer restrictions

## Troubleshooting

If you encounter any issues:

1. Ensure Chrome browser is up to date
2. Check that all required packages are installed correctly
3. Verify your internet connection is stable
4. Try restarting the backend server
5. Clear your browser cache
6. Check the console for any error messages

## Security Considerations

- The application implements rate limiting
- Uses secure headers and CORS policies
- Implements input validation and sanitization
- Follows security best practices for web scraping

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for educational purposes only. Please respect the terms of service of the retailers' websites. The developers are not responsible for any misuse of this tool. 