# Cortex XSIAM Platform APIs

**Confidential - Copyright © Palo Alto Networks**

## Table of Contents

1. [Asset Groups](#1-asset-groups)
    1.1. [Get all or filtered asset groups](#11-get-all-or-filtered-asset-groups)
    1.2. [Create an Asset Group](#12-create-an-asset-group)
    1.3. [Update an Asset Group](#13-update-an-asset-group)
    1.4. [Delete an Asset Group](#14-delete-an-asset-group)

---

## 1. Asset Groups

APIs for managing asset groups.

### 1.1 Get all or filtered asset groups

**Endpoint:** `POST /public_api/v1/asset-groups`

By grouping assets based on shared attributes, you can address them collectively. Asset groups enable more efficient bulk actions and simplifies both filtering and scoping within the inventory and across the platform.

**Description:** Get all or filtered asset groups.

**Required License:** Cortex XSIAM Premium or Cortex XSIAM Enterprise or Cortex XSIAM NG SIEM or Cortex XSIAM Enterprise Plus.

#### Request Examples

**Bash (curl):**

```bash
curl -X 'POST' \
  'https://api-yourfqdn/public_api/v1/asset-groups' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "filters": {
    "AND": [
      {
        "SEARCH_FIELD": "XDM.ASSET_GROUP.TYPE",
        "SEARCH_TYPE": "EQ",
        "SEARCH_VALUE": "Dynamic"
      }
    ]
  },
  "sort": [
    {
      "FIELD": "XDM.ASSET_GROUP.LAST_UPDATE_TIME",
      "ORDER": "DESC"
    }
  ],
  "search_from": 0,
  "search_to": 1000
}'
```

**Python:**

```python
import http.client

conn = http.client.HTTPSConnection("api-yourfqdn")

payload = "{\"filters\":{\"AND\":[{\"SEARCH_FIELD\":\"XDM.ASSET_GROUP.TYPE\",\"SEARCH_TYPE\":\"EQ\",\"SEARCH_VALUE\":\"Dynamic\"}]},\"sort\":[{\"FIELD\":\"XDM.ASSET_GROUP.LAST_UPDATE_TIME\",\"ORDER\":\"DESC\"}],\"search_from\":0,\"search_to\":1000}"

headers = { 'content-type': "application/json" }

conn.request("POST", "/public_api/v1/asset-groups", payload, headers)

res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))
```

**Ruby:**

```ruby
require 'uri'
require 'net/http'
require 'openssl'

url = URI("https://api-yourfqdn/public_api/v1/asset-groups")
http = Net::HTTP.new(url.host, url.port)
http.use_ssl = true
http.verify_mode = OpenSSL::SSL::VERIFY_NONE

request = Net::HTTP::Post.new(url)
request["content-type"] = 'application/json'
request.body = "{\"filters\":{\"AND\":[{\"SEARCH_FIELD\":\"XDM.ASSET_GROUP.TYPE\",\"SEARCH_TYPE\":\"EQ\",\"SEARCH_VALUE\":\"Dynamic\"}]},\"sort\":[{\"FIELD\":\"XDM.ASSET_GROUP.LAST_UPDATE_TIME\",\"ORDER\":\"DESC\"}],\"search_from\":0,\"search_to\":1000}"

response = http.request(request)
puts response.read_body
```

**JavaScript (XMLHttpRequest):**

```javascript
const data = JSON.stringify({
  "filters": {
    "AND": [
      {
        "SEARCH_FIELD": "XDM.ASSET_GROUP.TYPE",
        "SEARCH_TYPE": "EQ",
        "SEARCH_VALUE": "Dynamic"
      }
    ]
  },
  "sort": [
    {
      "FIELD": "XDM.ASSET_GROUP.LAST_UPDATE_TIME",
      "ORDER": "DESC"
    }
  ],
  "search_from": 0,
  "search_to": 1000
});

const xhr = new XMLHttpRequest();
xhr.withCredentials = true;

xhr.addEventListener("readystatechange", function () {
  if (this.readyState === this.DONE) {
    console.log(this.responseText);
  }
});

xhr.open("POST", "https://api-yourfqdn/public_api/v1/asset-groups");
xhr.setRequestHeader("content-type", "application/json");

xhr.send(data);
```

**Java (Unirest):**

```java
HttpResponse<String> response = Unirest.post("https://api-yourfqdn/public_api/v1/asset-groups")
  .header("content-type", "application/json")
  .body("{\"filters\":{\"AND\":[{\"SEARCH_FIELD\":\"XDM.ASSET_GROUP.TYPE\",\"SEARCH_TYPE\":\"EQ\",\"SEARCH_VALUE\":\"Dynamic\"}]},\"sort\":[{\"FIELD\":\"XDM.ASSET_GROUP.LAST_UPDATE_TIME\",\"ORDER\":\"DESC\"}],\"search_from\":0,\"search_to\":1000}")
  .asString();
```

**Swift:**

```swift
import Foundation

let headers = ["content-type": "application/json"]
let parameters = [
  "filters": [
    "AND": [
      [
        "SEARCH_FIELD": "XDM.ASSET_GROUP.TYPE",
        "SEARCH_TYPE": "EQ",
        "SEARCH_VALUE": "Dynamic"
      ]
    ]
  ],
  "sort": [
    [
      "FIELD": "XDM.ASSET_GROUP.LAST_UPDATE_TIME",
      "ORDER": "DESC"
    ]
  ],
  "search_from": 0,
  "search_to": 1000
] as [String : Any]

let postData = JSONSerialization.data(withJSONObject: parameters, options: [])

let request = NSMutableURLRequest(url: NSURL(string: "https://api-yourfqdn/public_api/v1/asset-groups")! as URL,
                                        cachePolicy: .useProtocolCachePolicy,
                                    timeoutInterval: 10.0)
request.httpMethod = "POST"
request.allHTTPHeaderFields = headers
request.httpBody = postData as Data

let session = URLSession.shared
let dataTask = session.dataTask(with: request as URLRequest, completionHandler: { (data, response, error) -> Void in
  if (error != nil) {
    print(error)
  } else {
    let httpResponse = response as? HTTPURLResponse
    print(httpResponse)
  }
})

dataTask.resume()
```

**PHP:**

```php
<?php
$curl = curl_init();

curl_setopt_array($curl, [
  CURLOPT_URL => "https://api-yourfqdn/public_api/v1/asset-groups",
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_ENCODING => "",
  CURLOPT_MAXREDIRS => 10,
  CURLOPT_TIMEOUT => 30,
  CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
  CURLOPT_CUSTOMREQUEST => "POST",
  CURLOPT_POSTFIELDS => "{\"filters\":{\"AND\":[{\"SEARCH_FIELD\":\"XDM.ASSET_GROUP.TYPE\",\"SEARCH_TYPE\":\"EQ\",\"SEARCH_VALUE\":\"Dynamic\"}]},\"sort\":[{\"FIELD\":\"XDM.ASSET_GROUP.LAST_UPDATE_TIME\",\"ORDER\":\"DESC\"}],\"search_from\":0,\"search_to\":1000}",
  CURLOPT_HTTPHEADER => [
    "content-type: application/json"
  ],
]);

$response = curl_exec($curl);
$err = curl_error($curl);

curl_close($curl);

if ($err) {
  echo "cURL Error #:". $err;
} else {
  echo $response;
}
```

**C:**

```c
CURL *hnd = curl_easy_init();

curl_easy_setopt(hnd, CURLOPT_CUSTOMREQUEST, "POST");
curl_easy_setopt(hnd, CURLOPT_URL, "https://api-yourfqdn/public_api/v1/asset-groups");

struct curl_slist *headers = NULL;
headers = curl_slist_append(headers, "content-type: application/json");
curl_easy_setopt(hnd, CURLOPT_HTTPHEADER, headers);

curl_easy_setopt(hnd, CURLOPT_POSTFIELDS, "{\"filters\":{\"AND\":[{\"SEARCH_FIELD\":\"XDM.ASSET_GROUP.TYPE\",\"SEARCH_TYPE\":\"EQ\",\"SEARCH_VALUE\":\"Dynamic\"}]},\"sort\":[{\"FIELD\":\"XDM.ASSET_GROUP.LAST_UPDATE_TIME\",\"ORDER\":\"DESC\"}],\"search_from\":0,\"search_to\":1000}");

CURLcode ret = curl_easy_perform(hnd);
```

**C#:**

```csharp
var client = new RestClient("https://api-yourfqdn/public_api/v1/asset-groups");
var request = new RestRequest(Method.POST);
request.AddHeader("content-type", "application/json");
request.AddParameter("application/json", "{\"filters\":{\"AND\":[{\"SEARCH_FIELD\":\"XDM.ASSET_GROUP.TYPE\",\"SEARCH_TYPE\":\"EQ\",\"SEARCH_VALUE\":\"Dynamic\"}]},\"sort\":[{\"FIELD\":\"XDM.ASSET_GROUP.LAST_UPDATE_TIME\",\"ORDER\":\"DESC\"}],\"search_from\":0,\"search_to\":1000}", ParameterType.RequestBody);
IRestResponse response = client.Execute(request);
```

#### Body Parameters (`application/json`)

*   `filters` (object):
    *   `AND` (array): Array of filter objects.
        *   `SEARCH_FIELD` (string): The field to search on (e.g., `XDM.ASSET_GROUP.TYPE`).
        *   `SEARCH_TYPE` (string): The type of search (e.g., `EQ`).
        *   `SEARCH_VALUE` (string): The value to search for (e.g., `Dynamic`).
*   `sort` (array):
    *   `FIELD` (string): Field to sort by (e.g., `XDM.ASSET_GROUP.LAST_UPDATE_TIME`).
    *   `ORDER` (string): Order of sort (`ASC` or `DESC`).
*   `search_from` (integer): Start index for pagination.
*   `search_to` (integer): End index for pagination (e.g., 1000).

#### Responses

**200 OK**

```json
[
  {
    "reply": {
      "data": [
        {}
      ],
      "metadata": {
        "filter_count": 1,
        "total_count": 1000
      }
    }
  }
]
```

**403 Unauthorized**

```json
[
  {
    "err_code": 403,
    "err_msg": "Forbidden. Access was denied to this resource.",
    "err_extra": "example"
  }
]
```

**500 Internal Server Error / Invalid Input**

```json
[
  {
    "err_code": 500,
    "err_msg": "An unexpected behavior occurred by Cortex Pubic API",
    "err_extra": "example"
  }
]
```

---

### 1.2 Create an Asset Group

**Endpoint:** `POST /public_api/v1/asset-groups/create`

**Description:** Create a dynamic Asset Group by specifying the filters, or a static group to manually include individual assets.

**Required License:** Cortex XSIAM Premium or Cortex XSIAM Enterprise or Cortex XSIAM NG SIEM or Cortex XSIAM Enterprise Plus.

#### Request Examples

**Bash (curl):**

```bash
curl -X 'POST' \
  'https://api-yourfqdn/public_api/v1/asset-groups/create' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "asset_group": {
    "group_name": "example",
    "group_type": "Dynamic",
    "group_description": "example",
    "membership_predicate": {
      "AND": [
        {
          "SEARCH_FIELD": "xdm.asset.type.class",
          "SEARCH_TYPE": "NEQ",
          "SEARCH_VALUE": "Other"
        }
      ]
    }
  }
}'
```

**Python:**

```python
import http.client

conn = http.client.HTTPSConnection("api-yourfqdn")

payload = "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}"

headers = { 'content-type': "application/json" }

conn.request("POST", "/public_api/v1/asset-groups/create", payload, headers)

res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))
```

**Ruby:**

```ruby
require 'uri'
require 'net/http'
require 'openssl'

url = URI("https://api-yourfqdn/public_api/v1/asset-groups/create")
http = Net::HTTP.new(url.host, url.port)
http.use_ssl = true
http.verify_mode = OpenSSL::SSL::VERIFY_NONE

request = Net::HTTP::Post.new(url)
request["content-type"] = 'application/json'
request.body = "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}"

response = http.request(request)
puts response.read_body
```

**JavaScript (XMLHttpRequest):**

```javascript
const data = JSON.stringify({
  "asset_group": {
    "group_name": "string",
    "group_type": "Dynamic",
    "group_description": "string",
    "membership_predicate": {
      "AND": [
        {
          "SEARCH_FIELD": "xdm.asset.type.class",
          "SEARCH_TYPE": "NEQ",
          "SEARCH_VALUE": "Other"
        }
      ]
    }
  }
});

const xhr = new XMLHttpRequest();
xhr.withCredentials = true;

xhr.addEventListener("readystatechange", function () {
  if (this.readyState === this.DONE) {
    console.log(this.responseText);
  }
});

xhr.open("POST", "https://api-yourfqdn/public_api/v1/asset-groups/create");
xhr.setRequestHeader("content-type", "application/json");

xhr.send(data);
```

**Java (Unirest):**

```java
HttpResponse<String> response = Unirest.post("https://api-yourfqdn/public_api/v1/asset-groups/create")
  .header("content-type", "application/json")
  .body("{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}")
  .asString();
```

**Swift:**

```swift
import Foundation

let headers = ["content-type": "application/json"]
let parameters = [
  "asset_group": [
    "group_name": "string",
    "group_type": "Dynamic",
    "group_description": "string",
    "membership_predicate": [
      "AND": [
        [
          "SEARCH_FIELD": "xdm.asset.type.class",
          "SEARCH_TYPE": "NEQ",
          "SEARCH_VALUE": "Other"
        ]
      ]
    ]
  ]
] as [String : Any]

let postData = JSONSerialization.data(withJSONObject: parameters, options: [])

let request = NSMutableURLRequest(url: NSURL(string: "https://api-yourfqdn/public_api/v1/asset-groups/create")! as URL,
                                        cachePolicy: .useProtocolCachePolicy,
                                    timeoutInterval: 10.0)
request.httpMethod = "POST"
request.allHTTPHeaderFields = headers
request.httpBody = postData as Data

let session = URLSession.shared
let dataTask = session.dataTask(with: request as URLRequest, completionHandler: { (data, response, error) -> Void in
  if (error != nil) {
    print(error)
  } else {
    let httpResponse = response as? HTTPURLResponse
    print(httpResponse)
  }
})

dataTask.resume()
```

**PHP:**

```php
<?php
$curl = curl_init();

curl_setopt_array($curl, [
  CURLOPT_URL => "https://api-yourfqdn/public_api/v1/asset-groups/create",
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_ENCODING => "",
  CURLOPT_MAXREDIRS => 10,
  CURLOPT_TIMEOUT => 30,
  CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
  CURLOPT_CUSTOMREQUEST => "POST",
  CURLOPT_POSTFIELDS => "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}",
  CURLOPT_HTTPHEADER => [
    "content-type: application/json"
  ],
]);

$response = curl_exec($curl);
$err = curl_error($curl);

curl_close($curl);

if ($err) {
  echo "cURL Error #:". $err;
} else {
  echo $response;
}
```

**C:**

```c
CURL *hnd = curl_easy_init();

curl_easy_setopt(hnd, CURLOPT_CUSTOMREQUEST, "POST");
curl_easy_setopt(hnd, CURLOPT_URL, "https://api-yourfqdn/public_api/v1/asset-groups/create");

struct curl_slist *headers = NULL;
headers = curl_slist_append(headers, "content-type: application/json");
curl_easy_setopt(hnd, CURLOPT_HTTPHEADER, headers);

curl_easy_setopt(hnd, CURLOPT_POSTFIELDS, "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}");

CURLcode ret = curl_easy_perform(hnd);
```

**C#:**

```csharp
var client = new RestClient("https://api-yourfqdn/public_api/v1/asset-groups/create");
var request = new RestRequest(Method.POST);
request.AddHeader("content-type", "application/json");
request.AddParameter("application/json", "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}", ParameterType.RequestBody);
IRestResponse response = client.Execute(request);
```

#### Body Parameters (`application/json`)

*   `asset_group` (object):
    *   `group_name` (string): Asset Group name.
    *   `group_type` (string, Enum): The type of Asset Group. Valid values:
        *   `Dynamic`: Assets grouped using filters. Any asset that meets the defined criteria is included.
        *   `Static`: Manually add individual assets to be included in a group.
    *   `group_description` (string): Optional description to clarify the purpose of the Asset Group.
    *   `membership_predicate` (object): Define the filter conditions for selecting which assets to be included in a dynamic Asset Group.

#### Responses

**200 OK**

```json
[
  {
    "reply": {
      "data": {
        "success": false,
        "asset_group_id": 1
      }
    }
  }
]
```

**403 Unauthorized**

```json
[
  {
    "err_code": 403,
    "err_msg": "Forbidden. Access was denied to this resource.",
    "err_extra": "example"
  }
]
```

**500 Internal Server Error / Invalid Input**

```json
[
  {
    "err_code": 500,
    "err_msg": "An unexpected behavior occurred by Cortex Pubic API",
    "err_extra": "example"
  }
]
```

---

### 1.3 Update an Asset Group

**Endpoint:** `POST /public_api/v1/asset-groups/update/{group_id}`

**Description:** Update the Asset Group specified by Asset Group ID.

**Required License:** Cortex XSIAM Premium or Cortex XSIAM Enterprise or Cortex XSIAM NG SIEM or Cortex XSIAM Enterprise Plus.

#### Path Parameters

*   `group_id` (string, required): Asset Group ID.

#### Request Examples

**Bash (curl):**

```bash
curl -X 'POST' \
  'https://api-yourfqdn/public_api/v1/asset-groups/update/{group_id}' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "asset_group": {
    "group_name": "example",
    "group_type": "Dynamic",
    "group_description": "example",
    "membership_predicate": {
      "AND": [
        {
          "SEARCH_FIELD": "xdm.asset.type.class",
          "SEARCH_TYPE": "NEQ",
          "SEARCH_VALUE": "Other"
        }
      ]
    }
  }
}'
```

**Python:**

```python
import http.client

conn = http.client.HTTPSConnection("api-yourfqdn")

payload = "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}"

headers = { 'content-type': "application/json" }

# Note: Replace %7Bgroup_id%7D with the actual group_id
conn.request("POST", "/public_api/v1/asset-groups/update/%7Bgroup_id%7D", payload, headers)

res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))
```

**Ruby:**

```ruby
require 'uri'
require 'net/http'
require 'openssl'

# Note: Replace %7Bgroup_id%7D with the actual group_id
url = URI("https://api-yourfqdn/public_api/v1/asset-groups/update/%7Bgroup_id%7D")
http = Net::HTTP.new(url.host, url.port)
http.use_ssl = true
http.verify_mode = OpenSSL::SSL::VERIFY_NONE

request = Net::HTTP::Post.new(url)
request["content-type"] = 'application/json'
request.body = "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}"

response = http.request(request)
puts response.read_body
```

**JavaScript (XMLHttpRequest):**

```javascript
const data = JSON.stringify({
  "asset_group": {
    "group_name": "string",
    "group_type": "Dynamic",
    "group_description": "string",
    "membership_predicate": {
      "AND": [
        {
          "SEARCH_FIELD": "xdm.asset.type.class",
          "SEARCH_TYPE": "NEQ",
          "SEARCH_VALUE": "Other"
        }
      ]
    }
  }
});

const xhr = new XMLHttpRequest();
xhr.withCredentials = true;

xhr.addEventListener("readystatechange", function () {
  if (this.readyState === this.DONE) {
    console.log(this.responseText);
  }
});

# Note: Replace %7Bgroup_id%7D with the actual group_id
xhr.open("POST", "https://api-yourfqdn/public_api/v1/asset-groups/update/%7Bgroup_id%7D");
xhr.setRequestHeader("content-type", "application/json");

xhr.send(data);
```

**Java (Unirest):**

```java
# Note: Replace %7Bgroup_id%7D with the actual group_id
HttpResponse<String> response = Unirest.post("https://api-yourfqdn/public_api/v1/asset-groups/update/%7Bgroup_id%7D")
  .header("content-type", "application/json")
  .body("{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}")
  .asString();
```

**Swift:**

```swift
import Foundation

let headers = ["content-type": "application/json"]
let parameters = [
  "asset_group": [
    "group_name": "string",
    "group_type": "Dynamic",
    "group_description": "string",
    "membership_predicate": [
      "AND": [
        [
          "SEARCH_FIELD": "xdm.asset.type.class",
          "SEARCH_TYPE": "NEQ",
          "SEARCH_VALUE": "Other"
        ]
      ]
    ]
  ]
] as [String : Any]

let postData = JSONSerialization.data(withJSONObject: parameters, options: [])

# Note: Replace %7Bgroup_id%7D with the actual group_id
let request = NSMutableURLRequest(url: NSURL(string: "https://api-yourfqdn/public_api/v1/asset-groups/update/%7Bgroup_id%7D")! as URL,
                                        cachePolicy: .useProtocolCachePolicy,
                                    timeoutInterval: 10.0)
request.httpMethod = "POST"
request.allHTTPHeaderFields = headers
request.httpBody = postData as Data

let session = URLSession.shared
let dataTask = session.dataTask(with: request as URLRequest, completionHandler: { (data, response, error) -> Void in
  if (error != nil) {
    print(error)
  } else {
    let httpResponse = response as? HTTPURLResponse
    print(httpResponse)
  }
})

dataTask.resume()
```

**PHP:**

```php
<?php
$curl = curl_init();

# Note: Replace %7Bgroup_id%7D with the actual group_id
curl_setopt_array($curl, [
  CURLOPT_URL => "https://api-yourfqdn/public_api/v1/asset-groups/update/%7Bgroup_id%7D",
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_ENCODING => "",
  CURLOPT_MAXREDIRS => 10,
  CURLOPT_TIMEOUT => 30,
  CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
  CURLOPT_CUSTOMREQUEST => "POST",
  CURLOPT_POSTFIELDS => "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}",
  CURLOPT_HTTPHEADER => [
    "content-type: application/json"
  ],
]);

$response = curl_exec($curl);
$err = curl_error($curl);

curl_close($curl);

if ($err) {
  echo "cURL Error #:". $err;
} else {
  echo $response;
}
```

**C:**

```c
CURL *hnd = curl_easy_init();

curl_easy_setopt(hnd, CURLOPT_CUSTOMREQUEST, "POST");
# Note: Replace %7Bgroup_id%7D with the actual group_id
curl_easy_setopt(hnd, CURLOPT_URL, "https://api-yourfqdn/public_api/v1/asset-groups/update/%7Bgroup_id%7D");

struct curl_slist *headers = NULL;
headers = curl_slist_append(headers, "content-type: application/json");
curl_easy_setopt(hnd, CURLOPT_HTTPHEADER, headers);

curl_easy_setopt(hnd, CURLOPT_POSTFIELDS, "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}");

CURLcode ret = curl_easy_perform(hnd);
```

**C#:**

```csharp
# Note: Replace %7Bgroup_id%7D with the actual group_id
var client = new RestClient("https://api-yourfqdn/public_api/v1/asset-groups/update/%7Bgroup_id%7D");
var request = new RestRequest(Method.POST);
request.AddHeader("content-type", "application/json");
request.AddParameter("application/json", "{\"asset_group\":{\"group_name\":\"string\",\"group_type\":\"Dynamic\",\"group_description\":\"string\",\"membership_predicate\":{\"AND\":[{\"SEARCH_FIELD\":\"xdm.asset.type.class\",\"SEARCH_TYPE\":\"NEQ\",\"SEARCH_VALUE\":\"Other\"}]}}}", ParameterType.RequestBody);
IRestResponse response = client.Execute(request);
```

#### Body Parameters (`application/json`)

*   `asset_group` (object):
    *   `group_name` (string): Asset Group name.
    *   `group_type` (string, Enum): The type of Asset Group (e.g., "Dynamic", "Static").
    *   `group_description` (string): Optional description.
    *   `membership_predicate` (object): Define filter conditions.

#### Responses

**200 OK**

```json
[
  {
    "reply": {
      "data": {
        "success": false
      }
    }
  }
]
```

**403 Unauthorized**

```json
[
  {
    "err_code": 403,
    "err_msg": "Forbidden. Access was denied to this resource.",
    "err_extra": "example"
  }
]
```

**500 Internal Server Error / Invalid Input**

```json
[
  {
    "err_code": 500,
    "err_msg": "An unexpected behavior occurred by Cortex Pubic API",
    "err_extra": "example"
  }
]
```

---

### 1.4 Delete an Asset Group

**Endpoint:** `POST /public_api/v1/asset-groups/delete/{group_id}`

**Description:** Delete the Asset Group specified by Asset Group ID.

**Required License:** Cortex XSIAM Premium or Cortex XSIAM Enterprise or Cortex XSIAM NG SIEM or Cortex XSIAM Enterprise Plus.

#### Path Parameters

*   `group_id` (string, required): Asset Group ID.

#### Request Examples

**Bash (curl):**

```bash
curl -X 'POST' \
  'https://api-yourfqdn/public_api/v1/asset-groups/delete/{group_id}' \
  -H 'Accept: application/json'
```

**Python:**

```python
import http.client

conn = http.client.HTTPSConnection("api-yourfqdn")

# Note: Replace %7Bgroup_id%7D with the actual group_id
conn.request("POST", "/public_api/v1/asset-groups/delete/%7Bgroup_id%7D")

res = conn.getresponse()
data = res.read()
print(data.decode("utf-8"))
```

**Ruby:**

```ruby
require 'uri'
require 'net/http'
require 'openssl'

# Note: Replace %7Bgroup_id%7D with the actual group_id
url = URI("https://api-yourfqdn/public_api/v1/asset-groups/delete/%7Bgroup_id%7D")
http = Net::HTTP.new(url.host, url.port)
http.use_ssl = true
http.verify_mode = OpenSSL::SSL::VERIFY_NONE

request = Net::HTTP::Post.new(url)
response = http.request(request)
puts response.read_body
```

**JavaScript (XMLHttpRequest):**

```javascript
const data = null;

const xhr = new XMLHttpRequest();
xhr.withCredentials = true;

xhr.addEventListener("readystatechange", function () {
  if (this.readyState === this.DONE) {
    console.log(this.responseText);
  }
});

# Note: Replace %7Bgroup_id%7D with the actual group_id
xhr.open("POST", "https://api-yourfqdn/public_api/v1/asset-groups/delete/%7Bgroup_id%7D");

xhr.send(data);
```

**Java (Unirest):**

```java
# Note: Replace %7Bgroup_id%7D with the actual group_id
HttpResponse<String> response = Unirest.post("https://api-yourfqdn/public_api/v1/asset-groups/delete/%7Bgroup_id%7D")
  .asString();
```

**Swift:**

```swift
import Foundation

# Note: Replace %7Bgroup_id%7D with the actual group_id
let request = NSMutableURLRequest(url: NSURL(string: "https://api-yourfqdn/public_api/v1/asset-groups/delete/%7Bgroup_id%7D")! as URL,
                                        cachePolicy: .useProtocolCachePolicy,
                                    timeoutInterval: 10.0)
request.httpMethod = "POST"

let session = URLSession.shared
let dataTask = session.dataTask(with: request as URLRequest, completionHandler: { (data, response, error) -> Void in
  if (error != nil) {
    print(error)
  } else {
    let httpResponse = response as? HTTPURLResponse
    print(httpResponse)
  }
})

dataTask.resume()
```

**PHP:**

```php
<?php
$curl = curl_init();

# Note: Replace %7Bgroup_id%7D with the actual group_id
curl_setopt_array($curl, [
  CURLOPT_URL => "https://api-yourfqdn/public_api/v1/asset-groups/delete/%7Bgroup_id%7D",
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_ENCODING => "",
  CURLOPT_MAXREDIRS => 10,
  CURLOPT_TIMEOUT => 30,
  CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
  CURLOPT_CUSTOMREQUEST => "POST",
]);

$response = curl_exec($curl);
$err = curl_error($curl);

curl_close($curl);

if ($err) {
  echo "cURL Error #:". $err;
} else {
  echo $response;
}
```

**C:**

```c
CURL *hnd = curl_easy_init();

curl_easy_setopt(hnd, CURLOPT_CUSTOMREQUEST, "POST");
# Note: Replace %7Bgroup_id%7D with the actual group_id
curl_easy_setopt(hnd, CURLOPT_URL, "https://api-yourfqdn/public_api/v1/asset-groups/delete/%7Bgroup_id%7D");

CURLcode ret = curl_easy_perform(hnd);
```

**C#:**

```csharp
# Note: Replace %7Bgroup_id%7D with the actual group_id
var client = new RestClient("https://api-yourfqdn/public_api/v1/asset-groups/delete/%7Bgroup_id%7D");
var request = new RestRequest(Method.POST);
IRestResponse response = client.Execute(request);
```

#### Responses

**200 OK**

```json
[
  {
    "reply": {
      "data": {
        "success": false
      }
    }
  }
]
```

**403 Unauthorized**

```json
[
  {
    "err_code": 403,
    "err_msg": "Forbidden. Access was denied to this resource.",
    "err_extra": "example"
  }
]
```

**500 Internal Server Error / Invalid Input**

```json
[
  {
    "err_code": 500,
    "err_msg": "An unexpected behavior occurred by Cortex Pubic API",
    "err_extra": "example"
  }
]
```
