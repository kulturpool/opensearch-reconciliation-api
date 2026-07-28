## Preliminary Documentation

Currently developing a framework which automatically downloads and indexes the GND. Based on this a reconciliation API is created, which can be used with OpenRefine and runs totally locally.
We use OpenSearch for indexing and searching the GND data.

Current State: Basic search and api functions have been implemented and tested with a little testset. Next steps are:
- creating reconciliation functionalities
- creating GND download functionalities
- Adapting code to work with big GND data
- Implement functionalities to include other data services

### Structure

### Files

api/services/search.py contains search and scoring functionalities using OpenSearch
- contains the main search function search\_gnd() that returns a list of candidate matches in OpenRefine readable format. 
- get\_gnd\_record\_by\_id() function to return a single GND record based on its ID, useful for the /preview functionality. Returns the record or None if none is found.
- It calls the build\_search\_body() function which builds the body of the query that is then passed to OpenSearch. 
- format\_search\_results() first creates the score by calling the normalize\_score() function, then it formats the results to fit with the OpenRefine format.
- The normalize\_score() function contains a preliminary way to calculate a score for the results. #TODO: Research original GND score calculation and adapt it accordingly.
- is\_likely\_match() returns a boolean value indicating whether the score is above a certain threshold. #TODO: Research the GND threshold
- format\_entity\_types() converts the entity to fit with the OpenRefine-format

api/main.py contains the API functionalities and definition of the GND_Types #TODO adapt GND types accordingly
- initializes the FastAPI and defines the get("/"), get("/health"), get("/preview/{gnd_id}"), get("/suggest/entity"), get("/suggest/type"), get("/suggest/property"), get("/reconcile") and post("/reconcile"), get("/extend") calls
- get("/") - service\_manifest() defines the API service and required fields etc. #TODO has to be adapted to include the whole GND space and not only person
- health() returns a status: ok if the service works
- preview() takes a gnd_id and returns a small HTML preview for OpenRefine or No record found as HTML if none is found. 
- suggest\_entity() takes a prefix which functions as query, and a type, which is then again given to the search_gnd() function. The results are then returned as suggestions.
- suggest\_type() suggests the supported entity types, if there is no prefix given then the first n gnd types are suggested, and otherwise it just checks if the id or prefix are in the GND_Types list we have defined and returns the results - also works with substrings
- suggest\_property() suggest supported properties, similar to the suggest\_type() function. 
- extend\_get() takes an GET-based extend request from OpenRefine and returns the output from handle\_extend\_request()
- extend\_post() calls parse\_and\_handle\_root\_post()
- handle\_extend\_request() takes the id and propertie ids as input and returns the propertie values for the given id. Also returns properties metadate, created by build\_extend\_meta(), which entails property id and name. Function loops through the ids and gets the records, and then passes them to build\_extend\_row(). Here the property values are transformed to OpenRefine extend call format and returned. #TODO: check how OpenRefine actually wants the extend format to look like and adapt accordingly.  
- reconcile\_get() takes queries (OpenRefine Style) and query (just a string). Checks if queries is json format and then processes them using handle\_reconcilation\_queries(). If query is given, it immediately gives it the search_gnd() function and returns the results. If neither of the two values is given, an error is returned.
- reconcile\_post() calls parse\_and\_handle\_root\_post()
- handle\_reconciliation\_queries() takes the queries as a dict in OpenRefine-style batched format and returns the results in OpenRefine format. Loops through the queries and passes them to search_gnd() and returns the results.
- extract\_entity\_type() extracts the optional reconciliation type from OpenRefine query object.
- render\_gnd\_preview() takes a record as dict and returns the html as string. It extracts all the information we want from the record. It calls several helper functions for rendering list_block, life_dates, value_block which are named render_list_block() etc. and defined in the same main.py file. #TODO think about whether we want to move those to some seperate file so we have a cleaner main.py file
Further there is also a escape_html() function to handle characters that could lead to problems in html.
*OPEN QUESTION:* for both GET and POST request we end up using the search_gnd() function which uses the .get() function. Is this the correct way to do it?
How does OpenRefine handle the preview thingy? Is it just giving the ID to the API, in the way we implemented our stuff now?
- parse\_and\_handle\_root\_post() takes the body from a POST-request and checks if it is valid json format and checks if the body contains queries. Also checks if "application/json" is in the request header and handles data accordingly then. Returns an error if the queries parameter is missing. Then checks if the queries are str or dict, otherwise an error is raised. If valid, queries are passed to the handle\_reconciliation\_queries() function and returned.

importer/download_gnd_lds.py contains the main functionalities for downloading the GND data.
Either the complete GND data can be downloaded, or seperate files for the six different types can be downloaded.

importer/index\_gnd.py also creates an get\_opensearch\_client() function #TODO: check if we need to create that here and in the search.py file or if only one time is enough.
Contains main OpenSearch based indexing functionalities.
*OPEN QUESTION:* Where is the index stored?
- create\_index.py creates the GND index using a basic mapping or deletes an old index and creates a new one #TODO check if the mapping is appropriate or if it can be improved - probably needs improvement if we include more than the person data from GND
- load\_records() loads the json file #TODO: adapt accordingly to the big GND data, might need some more clever loading strategy for huge files
- normalize\_record() checks if record contains required fields and brings them to the same format #TODO adapt to include also other GND entities and not just persons
- generate\_bulk\_actions() loops through the records and yields the values after record normalization
- index\_records() uses the opensearchpy.helper.bulk() function to normalize the records and index them with indices.refresh
- main() takes the parser arguments, initializes the opensearch client and checks the connection, loads the data, creates the index and indexes the data.

importer/inspect\_gnd\_lds.py gives us information about the downloaded GND files (for development only)

importer/normalize\_gnd\_lds.py contains functionalities to map the downloaded GND data to our OpenSearch scheme.


### How to start

``` python importer/index_gnd.py --recreate ``` 
Creating the index
``` python -c "from api.services.search import search_gnd; print(search_gnd('Johann Wolfgang Goethe'))" ```
Searching for one person using the API
``` uvicorn api.main:app --host 0.0.0.0 --port 8083 --reload ```
Starting the FastAPI in the DevContainer, port can also be changed.
``` curl http://localhost:8083/health ```
Health checking the FastAPI in another terminal in the DevContainer, change port accordingly. Should return {"status":"ok"}
``` curl "http://localhost:8083/reconcile?query=Goethe" ```
Simple query test.
``` curl "http://localhost:8083/reconcile?queries=%7B%22q1%22%3A%7B%22query%22%3A%22Goethe%22%7D%7D" ```
OpenRefine GET-test. Query represents this JSON: {"q1": {"query": "Goethe"}}
``` 
curl -X POST "http://localhost:8083/reconcile" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode 'queries={"q1":{"query":"Goethe"},"q2":{"query":"Mark Twain"}}' 
```
OpenRefine POST-test
``` curl http://localhost:8083/preview/118540238 ```
Getting the preview of a record based on its ID
After starting the FastAPI in the Container we can access the Service in OpenRefine by Adding Standard Reconciliation Service and adding this link: 
``` http://127.0.0.1:8083 ```

For Downloading the individual source files from GND
```
python importer/download_gnd_lds.py --source geografikum
python importer/download_gnd_lds.py --source koerperschaft
python importer/download_gnd_lds.py --source kongress
python importer/download_gnd_lds.py --source person
python importer/download_gnd_lds.py --source sachbegriff
python importer/download_gnd_lds.py --source werk
```
For downloading all the source files from GND
```
python importer/download_gnd_lds.py --source all
```
To redownload existing files: 
```
python importer/download_gnd_lds.py --source sachbegriff --force
```
Creating the index for the file:
```
python -m indexer.index_gnd_lds --source sachbegriff --recreate
python -m indexer.index_gnd_lds --source geografikum
python -m indexer.index_gnd_lds --source werk
python -m indexer.index_gnd_lds --source koerperschaft
python -m indexer.index_gnd_lds --source kongress
python -m indexer.index_gnd_lds --source person
```
Important is to use --recreate only for the first import otherwise the index gets reset for every import.
