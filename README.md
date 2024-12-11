**Closet API**

The Closet API is a RESTful web service for managing clothing items, outfits, and their ratings. It integrates with OpenWeatherMap to fetch weather data and filter outfits based on location-specific conditions.

**Features:**

Manage clothing items with attributes like type, color, and waterproof status.

Create, retrieve, and delete outfits made up of clothing items.

Rate outfits and view the top-rated ones.

Automatically filter outfits based on weather conditions using OpenWeatherMap.

Dockerized application for easy deployment.

**Technologies Used:**

Python: Flask & Flask-RESTful for building the API.

MongoDB: NoSQL database for storing clothes, outfits, and ratings.

Docker Compose: For containerized deployment.

OpenWeatherMap API: For weather data integration.

**Getting Started:**

To run this API locally, follow these steps:

1. Make sure you have Docker and Docker Compose installed on your machine.

2. Hold a valid OpenWeatherMap API key (Sign Up for OpenWeatherMap -> Generate an API Key -> Add the API Key to line 20 in the code).

3. Clone the repository:
git clone https://github.com/AdiBenZion9/Closet-Management.git

**Run the application with Docker Compose:**

cd Closet-Management

docker-compose up

The API will be available at http://localhost:5000.

**API Endpoints**

Clothes

POST /clothes - Add a new clothing item.

GET /clothes - Retrieve all clothing items.

GET /clothes?query=<value> - Retrieve a specific clothing item by specific field.

DELETE /clothes?query=<value> - Delete a specific clothing item by specific field.

Outfits

POST /outfits - Add a new outfit.

GET /outfits - Retrieve all outfits that match the current weather according to OpenWeatherMap and computer IP.

GET /outfits?query=<value> - Retrieve a specific outfit by specific field.

DELETE /outfits?query=<value> - Delete a specific outfit by specific field.

Ratings

GET /ratings - Retrieve all ratings for outfits.

GET /ratings?id=<id> - Retrieve ratings for a specific outfit by ID.

POST /ratings?id=<id> - Add a rating for a specific outfit.

DELETE /ratings?id=<id> - Delete ratings for a specific outfit by ID.

Top Outfits

GET /top - Retrieve the top-rated outfits.
