import pymongo
from flask import Flask, request
from flask_restful import Api, Resource
from urllib.parse import urlparse
import requests
import uuid

app = Flask(__name__)
api = Api(app)

# Connect to MongoDB
client = pymongo.MongoClient("mongodb://mongo:27017/")
db = client["Closet"]
clothes_collection = db["Clothes"]
outfits_collection = db["Outfits"]
ratings_collection = db["Ratings"]
clothes_ids = db["ClothesIds"]

# OpenWeatherMap API setup
OPENWEATHER_API_KEY = 'insert_here_your_openweather_api_key'
OPENWEATHER_URL = 'https://api.openweathermap.org/data/2.5/weather'
IPINFO_URL = 'https://ipinfo.io/json'


class Clothes(Resource):
    def get(self):
        args = request.args
        try:
            if args:
                query = {key: value for key, value in args.items()}
                filtered_clothes = list(clothes_collection.find(query, {'_id': 0}))
            else:
                filtered_clothes = list(clothes_collection.find({}, {'_id': 0}))
            return filtered_clothes, 200
        except Exception as e:
            return {'Error fetching data': str(e)}, 500

    def post(self):
        try:
            # Check if the mediaType is JSON
            if request.headers['Content-Type'] != 'application/json':
                return {'error': 'Unsupported Media Type: Only JSON is supported.'}, 415

            data = request.json

            # Check if there's a missing field
            if not all(field in data for field in ['type', 'color', 'photo']):
                return {'message': 'Unprocessable entity: Missing required fields'}, 422

            if not data['type'].split() or not data['color'].split() \
                    or not data['photo'].split():
                return {'message': 'Unprocessable entity: Empty fields are not accepted'}, 422

            # Check for invalid image url
            if not is_valid_url(data['photo']):
                return {'message': 'Unprocessable entity: invalid url'}, 422
            
            # Check for duplicate photo URL
            if clothes_collection.find_one({'photo': data['photo']}):
                return {'message': 'Unprocessable entity: Duplicate photo URL. Each clothing item must be unique.'}, 422

            # Check for invalid type
            accepted_types = ['Dress', 'Shirt', 'Long Pants', 'Short Pants', 'Skirt', 'Shoes', 'Jacket', 'Bag', 'Hat',
                              'Belt', 'Scarf', 'SunGlasses']
            if data['type'] not in accepted_types:
                return {'message': 'Unprocessable entity: Invalid type value'}, 422

            while True:
                piece_id = str(uuid.uuid4())  # generate a unique id for each piece
                if clothes_ids.find_one({'PieceID': piece_id}) is None:
                    clothes_ids.insert_one({'PieceID': piece_id})
                    break

            piece = {
                'type': data['type'],  # such as: dress, pants, shirt, etc
                'color': data['color'],
                'waterProof': data.get('waterProof', False),
                'photo': data['photo'],
                'id': piece_id
            }
            clothes_collection.insert_one(piece)
            return {'created': piece_id}, 201

        except Exception as e:
            return {'Invalid JSON file': str(e)}, 422

class FilteredClothes(Resource):
    def get(self, id):
        piece = clothes_collection.find_one({'id': id}, {'_id': 0})
        if not piece:
            return {'message': 'Not Found: piece not found'}, 404
        return piece, 200

    def get(self, type=None, color=None, waterProof=None):
        # Build the query based on the parameters provided
        query = {}
        if type:
            query['type'] = type
        if color:
            query['color'] = color
        if waterProof:
            query['waterProof'] = waterProof

        # Perform the search with the constructed query
        pieces = list(clothes_collection.find(query, {'_id': 0}))

        if not pieces:
            return {'message': 'Not Found: no pieces matching the criteria found'}, 404
        else:
            photos = [piece['photo'] for piece in pieces]
            return photos, 200
    
    def delete(self, id):
        try:
            # Retrieve the photo URL of the clothing item using the given id
            clothing_item = clothes_collection.find_one({'id': id}, {'photo': 1, '_id': 0})
            if not clothing_item:
                return {'message': 'Not Found: clothing item not found'}, 404
            
            photo_url = clothing_item['photo']

            # Delete the clothing item
            clothes_collection.delete_one({'id': id})

            # Find all outfits where the photo URL is in the outfitPhoto list
            outfits_with_photo = list(outfits_collection.find({'outfitPhoto': photo_url}, {'id': 1, '_id': 0}))
            
            # Extract outfit IDs for deleting associated ratings
            outfit_ids = [outfit['id'] for outfit in outfits_with_photo]

            # Delete outfits containing the photo URL
            outfits_collection.delete_many({'outfitPhoto': photo_url})

            # Delete ratings associated with the deleted outfits
            ratings_collection.delete_many({'id': {'$in': outfit_ids}})

            return {
                'message': 'Clothing item, associated outfits, and related ratings successfully deleted',
                'id': id,
                'deletedPhoto': photo_url
            }, 200

        except Exception as e:
            return {'error': str(e)}, 500

    # Only to change photo urls
    def put(self, id):
        try:
            # Check if the mediaType is JSON
            if request.headers['Content-Type'] != 'application/json':
                return {'error': 'Unsupported Media Type: Only JSON is supported.'}, 415

            data = request.json

            # Check if the 'photo' field is provided
            if 'photo' not in data:
                return {'message': 'Unprocessable entity: Missing photo field'}, 422

            # Validate the URL for the photo
            if not is_valid_url(data['photo']):
                return {'message': 'Unprocessable entity: Invalid photo URL'}, 422

            # Find the existing piece by its ID
            existing_piece = clothes_collection.find_one({'id': id})
            if not existing_piece:
                return {'message': 'Not Found: Piece not found'}, 404

            # Update the photo URL of the existing piece
            clothes_collection.update_one(
                {'id': id},
                {'$set': {'photo': data['photo']}}  # Only update the photo field
            )

            return {'message': 'Piece photo updated successfully', 'id': id}, 200

        except Exception as e:
            return {'Invalid JSON file': str(e)}, 422


class Outfits(Resource):
    def get(self):
        args = request.args
        try:
            # Initialize an empty query
            query = {}

            # Get the query parameters
            clothing_type = args.get('type')
            style = args.get('style')
            outfit_id = args.get('id')

            # Automatically get the user's location based on their IP address
            lat_lon = get_location_from_ip(self)
            if not lat_lon:
                return {'message': 'Could not determine location from IP address'}, 500

            # Fetch the current weather based on the user's location
            lat, lon = lat_lon
            should_be_waterproof, current_weather = fetch_weather(self, lat, lon)
            if should_be_waterproof is None or current_weather is None:
                return {'message': 'Could not fetch data'}, 500

            if style:
                query['style'] = style

            query['waterproof'] = should_be_waterproof

            query['suitableWeathers'] = current_weather  # cold, mild, hot

            if outfit_id:
                query['id'] = outfit_id

            # Perform the query to find matching outfits
            filtered_outfits = list(outfits_collection.find(query, {'_id': 0}))

            print_waterproof = "need" if should_be_waterproof else "don't need"
            if not filtered_outfits:
                return {'message': f'The weather is {current_weather}, and we {print_waterproof} waterproof clothes, No outfits found matching this criteria'}, 404
            
            items = []
            for outfit in filtered_outfits:
                outfit['clothingItems'] = [{'type': item['type']} for item in outfit['clothingItems']]
                items.extend(item['type'] for item in outfit['clothingItems'])
                outfit['clothingItems'] = items
                items = []

            if clothing_type:
                out = []
                for outfit in filtered_outfits:
                    if clothing_type in outfit['clothingItems']:
                        out.append(outfit)

                filtered_outfits = out
            return filtered_outfits, 200

        except Exception as e:
            return {'Error fetching data': str(e)}, 500

    def post(self):
        try:
            # Check if the mediaType is JSON
            if request.headers['Content-Type'] != 'application/json':
                return {'error': 'Unsupported Media Type: Only JSON is supported.'}, 415

            data = request.json

            # Check if there's a missing field
            if not all(field in data for field in ['style', 'clothingItems', 'suitableWeathers']):
                return {'message': 'Unprocessable entity: Missing required fields'}, 422

            clothing_item_ids = data['clothingItems']

            # Validate that clothingItems is not empty
            if not clothing_item_ids:
                return {'message': 'Unprocessable entity: clothingItems must contain at least one ID'}, 422

            # Retrieve clothing items from the database
            clothing_items = list(clothes_collection.find(
                {'id': {'$in': clothing_item_ids}},
                {'_id': 0, 'type': 1, 'photo': 1}
            ))

            # Check that all provided IDs exist in the database
            if len(clothing_items) != len(clothing_item_ids):
                return {'message': 'Unprocessable entity: One or more clothing item IDs are invalid'}, 422

            # Validate clothing items based on their types
            item_types = ['Bag', 'Hat', 'Belt', 'Scarf', 'Sunglasses', 'Shoes', 'Jacket', 'Dress', 'Shirt',
                        'Long Pants', 'Short Pants', 'Skirt']
            item_counts = {item: 0 for item in item_types}

            for item in clothing_items:
                item_type = item['type']
                if item_type in item_types:
                    item_counts[item_type] += 1

            # Check for item count validations
            if item_counts['Shoes'] < 1:
                return {'message': 'You should have a pair of shoes!'}, 422

            # Check for at least one top (either Shirt or Dress)
            if item_counts['Shirt'] < 1 and item_counts['Dress'] < 1:
                return {'message': 'You should have at least one top!'}, 422

            # Check for at least one bottom if no Dress is present
            if item_counts['Dress'] < 1 and (
                    item_counts['Long Pants'] + item_counts['Short Pants'] + item_counts['Skirt']) < 1:
                return {'message': 'You should have at least one bottom!'}, 422
            
            #
            if item_counts['Long Pants'] + item_counts['Short Pants'] + item_counts['Skirt'] + item_counts['Dress'] > 1:
                return {'message':'Too many bottoms!'}, 422
                
            if item_counts['Shirt'] + item_counts['Dress'] > 1:
                return {'message':'Too many tops!'}, 422
            
            # Check that no item type exceeds the limit of one (except accessories like Bag, Hat, etc., if allowed)
            for item, count in item_counts.items():
                if count > 1:
                    return {'message': f'Too many {item}s!'}, 422
                

            # Check for invalid style
            accepted_styles = ['Casual', 'Elegant', 'Sporty', 'Party', 'Work']
            if data['style'] not in accepted_styles:
                return {'message': 'Unprocessable entity: Invalid style value'}, 422

            # Check for invalid suitableWeathers
            accepted_weathers = ['Cold', 'Mild', 'Hot']
            if data['suitableWeathers'] not in accepted_weathers:
                return {'message': 'Unprocessable entity: Invalid weather value'}, 422

            # Generate a unique ID for the outfit
            while True:
                outfit_id = str(uuid.uuid4())
                if outfits_collection.find_one({'id': outfit_id}) is None:
                    break

            # Determine whether the outfit should be marked as waterproof
            waterproof = any(item['type'] == 'Jacket' and item.get('waterProof', False) for item in clothing_items)

            # Prepare the outfit document
            pictures = [item['photo'] for item in clothing_items]
            outfit = {
                'style': data['style'],
                'waterproof': waterproof,
                'clothingItems': clothing_items,
                'suitableWeathers': data['suitableWeathers'],
                'outfitPhoto': pictures,
                'id': outfit_id
            }

            # Insert the outfit into the database
            outfits_collection.insert_one(outfit)

            # Create a rating space for the outfit
            ratings_collection.insert_one({'id': outfit_id, 'pictures': pictures})
            return {'Outfit added successfully to your closet!': outfit_id}, 201

        except Exception as e:
            return {'Invalid JSON file': str(e)}, 422

class FilteredOutfit(Resource):
    def get(self, id):
        # Find the outfit by its ID
        outfit = outfits_collection.find_one({'id': id}, {'_id': 0})
        if not outfit:
            return {'message': 'Not Found: outfi not found'}, 404
        return outfit, 200

    def get(self, style=None, piece_id=None):
        # Build the query based on the path parameters provided
        query = {}
        if style:
            query['style'] = style
        if piece_id:
            # Find all outfits where 'clothing_items' contains 'piece_id'
            query['clothing_items'] = piece_id

        # Perform the query to find matching outfits
        outfits = list(outfits_collection.find(query, {'_id': 0}))

        if not outfits:
            return {'message': 'Not Found: no outfits matching the criteria found'}, 404

        # Return the list of matching outfits
        return outfits, 200
    
    def delete(self, id):
        # find the outfit by its ID
        delete_result = outfits_collection.delete_one({'id': id})
        # Check if the outfit was found
        if delete_result.deleted_count == 0:
            return {'message': 'Outfit not found'}, 404
        # Delete the associated rating
        delete_rating_result = ratings_collection.delete_one({'id': id})
        if delete_rating_result.deleted_count == 0:
            return {'message': 'Rating not found'}, 404
        # Return a success message
        return {'message': 'Outfit successfully deleted', 'id': id}, 200
    
    def put(self, id):
        try:
            # Check if the outfit exists
            existing_outfit = outfits_collection.find_one({'id': id})
            if not existing_outfit:
                return {'message': 'Not Found: Outfit not found'}, 404

            # Check if the mediaType is JSON
            if request.headers['Content-Type'] != 'application/json':
                return {'error': 'Unsupported Media Type: Only JSON is supported.'}, 415

            data = request.json

            # Check if there's a missing field
            if not all(field in data for field in ['style', 'clothingItems', 'suitableWeathers']):
                return {'message': 'Unprocessable entity: Missing required fields'}, 422

            clothing_item_ids = data['clothingItems']

            # Validate that clothingItems is not empty
            if not clothing_item_ids:
                return {'message': 'Unprocessable entity: clothingItems must contain at least one ID'}, 422

            # Retrieve clothing items from the database
            clothing_items = list(clothes_collection.find(
                {'id': {'$in': clothing_item_ids}},
                {'_id': 0, 'type': 1, 'photo': 1}
            ))

            # Check that all provided IDs exist in the database
            if len(clothing_items) != len(clothing_item_ids):
                return {'message': 'Unprocessable entity: One or more clothing item IDs are invalid'}, 422

            # Validate clothing items based on their types
            item_types = ['Bag', 'Hat', 'Belt', 'Scarf', 'Sunglasses', 'Shoes', 'Jacket', 'Dress', 'Shirt',
                        'Long Pants', 'Short Pants', 'Skirt']
            item_counts = {item: 0 for item in item_types}

            for item in clothing_items:
                item_type = item['type']
                if item_type in item_types:
                    item_counts[item_type] += 1

            # Check for item count validations
            if item_counts['Shoes'] < 1:
                return {'message': 'You should have a pair of shoes!'}, 422

            # Check for at least one top (either Shirt or Dress)
            if item_counts['Shirt'] < 1 and item_counts['Dress'] < 1:
                return {'message': 'You should have at least one top!'}, 422

            # Check for at least one bottom if no Dress is present
            if item_counts['Dress'] < 1 and (
                    item_counts['Long Pants'] + item_counts['Short Pants'] + item_counts['Skirt']) < 1:
                return {'message': 'You should have at least one bottom!'}, 422

            if item_counts['Long Pants'] + item_counts['Short Pants'] + item_counts['Skirt'] + item_counts['Dress'] > 1:
                return {'message': 'Too many bottoms!'}, 422

            if item_counts['Shirt'] + item_counts['Dress'] > 1:
                return {'message': 'Too many tops!'}, 422

            # Check for invalid style
            accepted_styles = ['Casual', 'Elegant', 'Sporty', 'Party', 'Work']
            if data['style'] not in accepted_styles:
                return {'message': 'Unprocessable entity: Invalid style value'}, 422

            # Check for invalid suitableWeathers
            accepted_weathers = ['Cold', 'Mild', 'Hot']
            if data['suitableWeathers'] not in accepted_weathers:
                return {'message': 'Unprocessable entity: Invalid weather value'}, 422

            # Determine whether the outfit should be marked as waterproof
            waterproof = any(item['type'] == 'Jacket' and item.get('waterProof', False) for item in clothing_items)

            # Prepare the outfit document for update
            pictures = [item['photo'] for item in clothing_items]
            updated_outfit = {
                'style': data['style'],
                'waterproof': waterproof,
                'clothingItems': clothing_items,
                'suitableWeathers': data['suitableWeathers'],
                'outfitPhoto': pictures
            }

            # Update the outfit in the database
            outfits_collection.update_one({'id': id}, {'$set': updated_outfit})

            # Update the rating's pictures
            ratings_collection.update_one({'id': id}, {'$set': {'pictures': pictures}}, upsert=True)

            return {'Outfit updated successfully!': id}, 200

        except Exception as e:
            return {'Invalid JSON file': str(e)}, 422

class Ratings(Resource):
    def get(self):
        ratings = list(ratings_collection.find({}, {'_id': 0}))
        return ratings, 200
    
class RatingsId(Resource):
    def get(self, id):
        # Find the rating by its ID
        rating = ratings_collection.find_one({'id': id}, {'_id': 0})
        if rating:
            return rating, 200
        else:
            return {'message': 'Not Found: outfit not found'}, 404

    def post(self, id):
        try:
            if request.headers['Content-Type'] != 'application/json':
                return {'error': 'Unsupported Media Type: Only JSON is supported.'}, 415

            data = request.json

            # Check if there's a missing field
            if 'score' not in data:
                return {'message': 'Unprocessable entity: You should enter a score field'}, 422

            score = data.get('score')

            if not 0 <= score <= 10:
                return {'message': 'Unprocessable entity: A score should be a in the range 0 to 10 integer'}, 422
            
            # Check if the outfit exists
            result = ratings_collection.find_one_and_update(
                {'id': id},
                {'$push': {'scores': data['score']}},
                return_document=pymongo.ReturnDocument.AFTER
            )
            # Calculate the average score
            if result:
                avg = sum(result['scores']) / len(result['scores'])
                ratings_collection.update_one({'id': id}, {'$set': {'average': avg}})
                return {'Current average': avg}, 201
            else:
                return {'message': 'Not Found: outfit not found'}, 404
        except Exception as e:
            return {'Missing score field': str(e)}, 422
        
    def delete(self, id):
        # Find the rating by its ID
        delete_rating_result = ratings_collection.delete_one({'id': id})
        if delete_rating_result.deleted_count == 0:
            return {'message': 'Ratings not found'}, 404
        return {'message': 'Ratings successfully deleted', 'id': id}, 200

class TopOutfits(Resource):
    def get(self):
        # Compute the top-rated outfits dynamically
        top_outfits = self.compute_top_outfits()

        if top_outfits:
            return top_outfits, 200
        else:
            return [], 200

    def compute_top_outfits(self):
        ratings = list(ratings_collection.find({'scores': {'$exists': True, '$not': {'$size': 0}}}))
        sorted_ratings = sorted(ratings, key=lambda x: x['average'], reverse=True)
        # Get the top 3 outfits
        top_outfits = sorted_ratings[:3]
        if len(sorted_ratings) > 3:
            threshold_average = top_outfits[-1]['average']
            additional_outfits = [r for r in sorted_ratings[3:] if r['average'] == threshold_average]
            top_outfits.extend(additional_outfits)

        result = [{
            'id': outfit['id'],
            'average': outfit['average'],
            'outfit picture': outfit['pictures'],
        } for outfit in top_outfits]
        return result



def fetch_weather(self, latitude, longitude):
    """
    Fetch current weather data from OpenWeatherMap based on latitude and longitude.
    Returns both the weather condition (e.g., "Rain", "Clear") and the temperature.
    """
    try:
        params = {
            'lat': latitude,
            'lon': longitude,
            'appid': OPENWEATHER_API_KEY,
            'units': 'metric'  # celsius
        }
        response = requests.get(OPENWEATHER_URL, params=params)
        # Check if the request was successful
        if response.ok:
            should_be_waterproof = False
            weather_data = response.json()
            weather_condition = weather_data['weather'][0]['main']  # General condition (e.g., "Rain", "Clear")
            temperature = weather_data['main']['temp']  # Current temperature in Celsius
            if weather_condition in ['Drizzle', 'Rain', 'Snow', 'Thunderstorm']:
                should_be_waterproof = True
            return should_be_waterproof, match_temp_to_outfit(self, temperature)
        else:
            return None, None
    except Exception as e:
        return None, None


def match_temp_to_outfit(self, temperature):
    if temperature < 15:  
        weather_condition = 'Cold'
    elif 15 <= temperature < 30:
        weather_condition = 'Mild'
    else:  
        weather_condition = 'Hot'
    return weather_condition


def get_location_from_ip(self):
    """
    Fetch the user's location (latitude and longitude) based on their IP address.
    Uses the ipinfo.io service to retrieve geolocation data.
    """
    try:
        response = requests.get(IPINFO_URL)
        if response.ok:
            location_data = response.json()
            # The 'loc' field contains "latitude,longitude"
            latitude, llongitudeon = location_data['loc'].split(',')
            return latitude, llongitudeon
        else:
            return None
    except Exception as e:
        return None

def is_valid_url(url):
    """
    Validates if the given URL is properly formatted and points to a valid image.
    """
    try:
        parsed = urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):  # Basic URL format validation
            return False
        
        # Check if the URL points to an image
        response = requests.get(url, timeout=5, stream=True)
        content_type = response.headers.get('Content-Type', '').lower()
        if response.status_code == 200 and 'image' in content_type:
            return True
    except Exception as e:
        print(f"Error validating URL: {e}")
    
    return False

api.add_resource(Clothes, "/clothes")
api.add_resource(FilteredClothes, "/clothes/<string:id>")
api.add_resource(Outfits, "/outfits")
api.add_resource(FilteredOutfit, "/outfits/<string:id>")
api.add_resource(RatingsId, "/ratings/<string:id>")
api.add_resource(Ratings, "/ratings")
api.add_resource(TopOutfits, "/top")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
