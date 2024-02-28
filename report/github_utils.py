"""
Utilities to interact with GitHub
"""
import os
import time
import logging, requests, json
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

class GitHubRepo():
    """Interact with a DraCor Github Repository"""

    __github_api_base_url = "https://api.github.com/"
    
    # This holds the once downloaded commits of a repository. They are the source of truth of the whole analysis.
    # This will be a list later
    __commits = None
    __commits_detailed = None

    # based on the commits at some point corpus versions are created. This is a dictionary with the commits as keys 
    __corpus_versions = None

    # GitHub API returns the "state" or however it is called of a folder. This dictionary holds these downloaded states of all versions.
    # the key is the commit 
    __data_folder_objects = None

    # Fields/columns that are available when requesting versions
    __corpus_version_data_fields = ["id", 
                  "running_number", 
                  "date_from", 
                  "date_until", 
                  "data_folder_name", 
                  "data_folder_github_url", 
                  "document_count",
                  "document_sizes_sum",
                  "documents_affected_count",
                  "documents_added_count",
                  "documents_removed_count",
                  "documents_renamed_count",
                  "documents_modified_count",
                  "non_document_files_affected_count"
                  ]
    
    # per version: how many files stem from which sources, e.g. Textgrid, Project Gutenberg
    __source_distributions = None

    # data returned by the API endpoint /corpora/{corpusname}
    # can be used to interpolate information from the latest corpus version to others, e.g. sources of 
    # individual files; no need to look into each file
    __latest_corpus_contents_from_api = None

    # Holds information about the sources for the corpus
    __sources = None


    def __init__(self,
                 github_access_token: str = None,
                 repository_owner: str = "dracor-org",
                 repository_name:str = None,
                 download_and_prepare_analysis = False,
                 import_commit_list: str = None,
                 import_commit_details: str = None ,
                 import_data_folder_objects: str = None,
                 import_corpus_versions: str = None
                 ):
        """Initialize
        
        Args:
            github_access_token (str, option): Github Personal Access Token
            repository_owner (str, optional): Owner of the repository. Defaults to 'dracor-org'
            repository_name (str, required): Name of the repository, e.g. 'gerdracor'
            download_and_prepare_analysis (bool, optional): Trigger downloading and preparing data for analysis
            import_commit_list (str, optional): Path to file containing a previously generated list of commits of a repository
            import_commit_details (str, optional): Path to a file containing a previously downloaded commit details
            import_data_folder_objects (str, optional): Path to a file containing previously stored data folder objects
            import_corpus_versions (str, optional): Path to a file containing (possibly enriched) corpus versions. Enrichment won't be triggered automatically.
        """
        
        if github_access_token:
            self.__github_access_token = github_access_token
        else:
            logging.warning("Should set a GitHub Access Token!")
        
        self.__repository_owner = repository_owner

        assert repository_name is not None, "Must supply a repository name!"
        
        self.__repository_name = repository_name

        if download_and_prepare_analysis == True:
            self.__fetch_and_prepare_analysis_data()

        if import_commit_list:
            self.import_commits(file=import_commit_list)
        
        if import_commit_details:
            self.import_detailed_commits(file=import_commit_details)
        
        if import_data_folder_objects: 
            self.import_data_folder_objects(file=import_data_folder_objects)
        
        if import_corpus_versions: 
            self.import_corpus_versions(file=import_corpus_versions)
        

    def api_get(self, 
                api_call: str = None,
                url: str = None,
                headers: dict = None,
                parse_json: bool = True,
                headers_only: bool = False,
                return_response_object: bool = False,
                wait_for_rate_limit_reset: bool = True,
                **kwargs):
        """Send GET requests to the GitHub API.

        Args:
            api_call (str, optional): endpoint and parameters that should be sent to the GitHub API.
            url (str, optional): Full URL to GET data from GitHub API. If provided, api_call will be ignored.
            headers (dict, optional): Headers to send with the GET request. If provided on class instance level,
                will include the "Authorization" field with value of the personal access token and thus send authorized
                requests.
            parse_json (bool, optional): Parse the response as JSON. Defaults to True.
            headers_only (bool, optional): get the HTTP-Headers only. Defaults to False.
            return_response_object (bool, optional): Get the requests response instead of the parsed results. Defaults to False.

        """
        # Base-URL of the GitHub API
        github_api_base_url = self.__github_api_base_url
        
        if self.__github_access_token is not None:
            if headers is not None:
                headers["Authorization"] = f"Bearer {self.__github_access_token}"
            else:
                headers = dict(
                    Authorization=f"Bearer {self.__github_access_token}"
                )

        if api_call is not None and url is None:
            request_url = f"{self.__github_api_base_url}{api_call}"
            logging.debug(f"Send GET request to GitHub: {request_url}")
        elif url is not None:
            request_url = url
            logging.debug(f"Provided full URL to send GET request to GitHub: {request_url}.")
        else:
            request_url = self.__github_api_base_url
            logging.debug(f"No specialized API call (api_call) provided. Will send GET request to GitHub API "
                          f" base url.")

        if headers is not None:
            r = requests.get(url=request_url, headers=headers)
        else:
            r = requests.get(url=request_url)

        # logging.debug(r.headers)
        if "X-RateLimit-Remaining" in r.headers:
            if int(r.headers["X-RateLimit-Remaining"]) == 0:
                logging.warning(f"Used up rate limit of {r.headers['X-RateLimit-Limit']}.")
                logging.debug(r.headers)
                
                if wait_for_rate_limit_reset is True:
                    resets_at_time = int(r.headers['X-RateLimit-Reset'])
                    logging.debug(f"Limit will reset at Unix Epoch: {str(resets_at_time)}")
                    current_unix_epoch = int(datetime.now().timestamp())
                    logging.debug(f"Current Unix Epoch: {str(current_unix_epoch)}")
                    remaining_seconds = resets_at_time - current_unix_epoch
                    logging.warning(f"Rate limit will reset in {str(remaining_seconds)} seconds. Will wait until then ...")

                    time.sleep(remaining_seconds + 60)
                    logging.warning(f"Resuming operation ... will fetch data from {request_url} next.")
                    if headers is not None:
                        r = requests.get(url=request_url, headers=headers)
                    else:
                        r = requests.get(url=request_url)
                else:
                    raise Exception(f"Used up GitHub API rate limit and don't want to wait because {wait_for_rate_limit_reset} is set to false.")

            elif 1 < int(r.headers["X-RateLimit-Remaining"]) < 5:
                logging.warning(f"Approaching maximum API calls (rate limit). Remaining: "
                                f" {r.headers['X-RateLimit-Remaining']}")
            elif int(r.headers["X-RateLimit-Remaining"] == 1):
                logging.warning(f"Reached rate limit of {r.headers['X-RateLimit-Limit']}.")
                if self.__github_access_token is None:
                    logging.warning("Requests to GitHub API are probably unauthorized. Provide a personal "
                                    "access token to get a higher rate limit. "
                                    "See: https://docs.github.com/en/authentication/"
                                    "keeping-your-account-and-data-secure/managing-your-personal-access-tokens"
                                    "#creating-a-personal-access-token-classic")

        if headers_only is True:
            logging.debug("Returning headers only")
            return r.headers
        
        if return_response_object is True:
            return r

        if r.status_code == 200:
            logging.debug(f"GET request to GitHub API was successful.")
            if parse_json is True:
                data = json.loads(r.text)
                return data
            else:
                return r.text
        # TODO implement the other status codes
        else:
            logging.debug(f"GET request was not successful. Server returned status code: {str(r.status_code)}.")
            logging.debug(r.text)
    
    def __parse_link_headers(self, headers):
        """ Parse HTTP Link headers
        expects requests object headers"""
        # this fails here if the rate limit is exceded
        # if this happens, there are no link headers...
        #logging.debug(headers)
        assert "Link" in headers, "No link headers available"

        link_headers= dict()

        links = headers["Link"].split(", ")
        for link in links:
            # extracting would be nicer as a regex....
            url = link.split("; ")[0].replace(">","").replace("<","")
            rel = link.split("; ")[1].replace('rel="','').replace('"','')
            link_headers[rel] = url
        
        return link_headers

    def get_commits(self, 
                    headers_only:bool = False,
                    force_download:bool = False):
        """Get commits"""
        
        if self.__commits is not None and force_download is False:
            return self.__commits
        else:
            logging.debug("Fetching commits from GitHub ...")

            api_call = f"repos/{self.__repository_owner}/{self.__repository_name}/commits"

            if headers_only is True:
                return self.api_get(api_call=api_call, headers_only=True)
        
            else:
                all_commits_list_of_lists = []
            
                has_pages_left = True
                # this will be used in the next round
                url = None

                while has_pages_left is True:
                    logging.debug(f"Will get results from {url}")
                    r = self.api_get(api_call=api_call, url=url, return_response_object=True)
                    link_headers = self.__parse_link_headers(r.headers)

                    if "next" not in link_headers:
                        # this is the exit condition
                        has_pages_left = False

                    parsed_commits = json.loads(r.text)
                    all_commits_list_of_lists.append(parsed_commits)

                    if "next" in link_headers:
                        url=link_headers["next"]
                    else:
                        logging.debug("Nothing more to get")
                        break
                
                logging.debug("Done fetching commits.")

                # flatten the list of lists...
                all_commits = []
            
                for commits_list in all_commits_list_of_lists:
                    for commit in commits_list:
                        all_commits.append(commit)
                
                # store them so no need to download again
                self.__commits = all_commits
            
                return all_commits
    
    def store_commits(self, 
                     folder_name:str = "export",
                     file_name: str = None):
        """Save the downloaded commits"""
        if self.__commits is None:
            logging.critical("No commits downloaded. Aborting.")
            raise Exception("No commits downloaded.")
        
        if file_name is None:
            file_name = f"{self.__repository_name}_commits"
    

        with open(f"{folder_name}/{file_name}.json", "w") as f:
            f.write(json.dumps(self.__commits))
    
    def import_commits(self,
                       file:str = None):
        """Import saved commits"""
        with open(file, "r") as f:
            data = json.load(f)
        
        self.__commits = data
        logging.info(f"Imported commits from {file}.")
    
    def __transform_commits_to_versions(self):
        """Create corpus version stubs from commits"""
        
        assert self.__commits, "Commits have not been loaded. This is expected here!"

        versions = dict()

        commits_reversed = self.__commits
        # reverse the list, last item in the commits history is actually the first version
        commits_reversed.reverse()
        n=0
        for item in commits_reversed:
            version = dict(
                id=item["sha"],
                running_number=n+1,
                date_from = item["commit"]["committer"]["date"]
            )
            # if it is not the very last
            if n+1 != len(commits_reversed):
                #get the date of the next
                version["date_until"] = commits_reversed[n+1]["commit"]["committer"]["date"]

            versions[item["sha"]] = version
            n=n+1

        self.__corpus_versions = versions
        logging.debug(f"Added basic information of {len(commits_reversed)} versions.")

    def get_corpus_versions(self):
        if self.__corpus_versions:
            return self.__corpus_versions
        else:
            self.__transform_commits_to_versions()
            return self.__corpus_versions

    def __fetch_xml_files_by_commit(self,
                                                commit:str = None,
                                                data_folder_name="tei"):
        """Get the documents (=tei files) in the data folder
        """
        assert commit is not None, "Must provide a commit sha!"
        assert self.__commits, "Commits must have been loaded!"
        
        # this is a way to get the commit from the list by commit sha
        commit_data = list(filter(lambda item: item["sha"] == commit, self.__commits))[0]
        #logging.debug(commit_data)
        
        # get the url of tree
        tree = commit_data["commit"]["tree"]
        # get the tree and then the hash of the tree of the sub-folder
        repository_root_folder = self.api_get(url=tree["url"])

        if type(repository_root_folder) == dict:
            if repository_root_folder["truncated"] is True:
                logging.warning("Not all items in the root folder of the repository are included in the response.")

            tree_objects_in_root_folder = repository_root_folder["tree"]
            data_folder_object_candidates = list(filter(lambda item: item["path"] == data_folder_name,
                                             tree_objects_in_root_folder))
            if len(data_folder_object_candidates) == 1:
                data_folder_object = data_folder_object_candidates[0]
                #logging.debug(data_folder_object)
                logging.debug(f"Found data folder '{data_folder_name}' in tree objects. "
                            f" sha: {data_folder_object['sha']}, url: {data_folder_object['url']}.")
                if self.__corpus_versions is not None:
                    self.__corpus_versions[commit]["data_folder_github_url"] = data_folder_object['url']
                    self.__corpus_versions[commit]["data_folder_name"] = data_folder_name
            else: 
                logging.debug(f"Could not find data folder {data_folder_name} of commit {commit}.")
                logging.debug(f"Trying to find alternative folder 'data' of commit {commit}.")
                data_folder_object_candidates = list(filter(lambda item: item["path"] == "data",
                                             tree_objects_in_root_folder))
                if len(data_folder_object_candidates) == 1:
                    logging.debug(f"Detected data folder 'data'. Will use this.")
                    data_folder_object = data_folder_object_candidates[0]
                    self.__corpus_versions[commit]["data_folder_github_url"] = data_folder_object['url']
                    self.__corpus_versions[commit]["data_folder_name"] = "data"
                else:
                    data_folder_object = None
                
        else:
            logging.warning(f"GET request to get the data '{data_folder_name}' folder failed!")
            data_folder_object = None

        if data_folder_object is not None:
            logging.debug(f"Getting files in the data folder.")
            parsed_data_folder_tree_object = self.api_get(url=data_folder_object["url"])

            # This is not the very best check in the world
            if type(parsed_data_folder_tree_object) == dict:

                if parsed_data_folder_tree_object["truncated"] is True:
                    logging.warning("The contents of the TEI folder are paged! Need to implement!")
                    raise Exception("Really need to implement this, data is not correct!")

                file_objects = parsed_data_folder_tree_object["tree"]
                logging.debug(f"Found {len(file_objects)} files in the data folder tree.")
                #logging.debug(file_objects)
                if self.__corpus_versions is not None:
                    self.__corpus_versions[commit]["document_count"] = len(file_objects)

        if file_objects is not None:
            playnames = []
            for file_object in file_objects:
                filename = file_object["path"]
                if ".xml" in filename:
                    playnames.append(filename.split(".xml")[0])
            logging.debug(playnames)
            if self.__corpus_versions is not None:
                self.__corpus_versions[commit]["playnames"] = playnames
    
    def add_files_to_versions(self, 
                              version=None, 
                              data_folder_name:str = "tei"):
        if version is None:
            commits = self.__corpus_versions.keys()
            for commit in commits:
                logging.debug(f"Fetching files for {commit}.")
                try:
                    self.__fetch_xml_files_by_commit(commit=commit, data_folder_name=data_folder_name)
                    logging.debug("Success!")
                except:
                    # this might fail for the early commits of a corpus, in the case of "gerdracor" 
                    # the folder is not called "tei" but "data"
                    logging.debug(f"Fetching files failed with data folder name {data_folder_name} for {commit}. Will try again with fallback data folder name 'data'.")
                    try:
                        self.__fetch_xml_files_by_commit(commit=commit, data_folder_name="data")
                        logging.debug("Success with fallback folder name!")
                    except:
                        logging.warning(f"Fetching files with data folder name {data_folder_name} and fallback 'data' failed for {commit}.")

        else:
            self.__fetch_xml_files_by_commit(commit=version, data_folder_name=data_folder_name)
    
    def get_corpus_version(self, version:str = None) -> dict:
        """Get data of a single corpus version
        
        Args:
            version (str, required): ID/commit id of the corpus version
        """
        if version and self.__corpus_versions:
            return self.__corpus_versions[version]
        else:
            return {}
    
    def store_corpus_versions(self, 
                     folder_name:str = "export",
                     file_name: str = None,
                     ensure_ascii: bool = False):
        """Save the downloaded corpus versions"""
        if self.__corpus_versions is None:
            logging.critical("No versions created. Aborting.")
            raise Exception("No versions created.")
        
        if file_name is None:
            file_name = f"{self.__repository_name}_corpus_versions"
    

        with open(f"{folder_name}/{file_name}.json", "w", encoding='utf8') as f:
            f.write(json.dumps(self.__corpus_versions, ensure_ascii=ensure_ascii))
    
    def import_corpus_versions(self,
                       file:str = None):
        """Import saved corpus versions"""
        with open(file, "r") as f:
            data = json.load(f)
        
        self.__corpus_versions = data
        logging.info(f"Imported versions from {file}.")

    def get_corpus_versions_as_dict(self,
                                fields:list = None) -> dict:
        
        """Get corpus version data as a dictionary (to be used as dataframe)
        
        Args:
            fields (list, optional): List of field values to include in the data frame
        """
        
        assert self.__corpus_versions, "Corpus Versions must be generated first!" 
    
        if fields is None:
            # include the standard fields
            fields = self.__corpus_version_data_fields

        data = dict()
    
        for field in fields:
            data[field] = []

        for key in self.__corpus_versions.keys():
            version = self.__corpus_versions[key] 
        
            for field in fields:
                if field in version:
                    data[field].append(version[field])
                else:
                    data[field].append(None)

        return data

    def get_corpus_versions_as_df(self, 
                                  columns:list = None,
                                  sort: bool = True,
                                  sort_by_column:str = "running_numbers") -> pd.DataFrame:
        """Get information on the versions as pandas data frame"""
        
        if columns is None:
            # use the default columns
            columns = self.__corpus_version_data_fields

        df = pd.DataFrame(self.get_corpus_versions_as_dict(fields=columns))
        
        # some conversions
        if "date_from" in columns:
            df["date_from"] = pd.to_datetime(df["date_from"])
        if "date_until" in columns:
            df["date_until"] = pd.to_datetime(df["date_until"])
        
        if sort == True and sort_by_column in columns:
            df = df.sort_values(sort_by_column)
        
        return df
    
    def plot_documents_in_corpus_versions(self, 
                                          xlabel:str = None, 
                                          ylabel:str = None,
                                          title:str = None):
        """Plot the number of documents in the corpus over time"""
        df = self.get_corpus_versions_as_df(columns=["date_from","document_count"]).set_index("date_from")
        if xlabel:
            plt.xlabel(xlabel)
        else:
            plt.xlabel("Year")

        if ylabel:
            plt.ylabel(ylabel)
        else:
            plt.ylabel("Documents")

        if title:
            plt.title(title)

        plt.plot(df["document_count"])

    def compare_files_of_versions(self, id_version_1, id_version_2) -> list:
        """Compare the files of two versions
        Uses date from values to determine which version is the earlier one and return a list of new plays 
        Identifies which version is earlier
        """
        assert self.__corpus_versions, "Expected that corpus versions are availale!"

        version_1 = self.__corpus_versions[id_version_1]
        version_2 = self.__corpus_versions[id_version_2]
        
        # identify, which one is earlier
        date_version_1 = datetime.fromisoformat(version_1["date_from"])
        date_version_2 = datetime.fromisoformat(version_2["date_from"])

        if date_version_1 < date_version_2:
            logging.debug("Version 1 is earlier.")
            earlier = version_1
            later = version_2
        else:
            logging.debug("Version 2 is ealier.")
            earlier = version_2
            later = version_1

        # We assume that the later has more plays...
        new_plays = []
        
        for playname in later["playnames"]:
            if playname not in earlier["playnames"]:
                new_plays.append(playname)

        return new_plays
    
    def add_new_play_info_to_corpus_versions(self):
        """Function to add the information to versions which plays are new compared to the earlier versions
        This does a pair-whise comparson of the later to the earlier version, if the later contains more files, 
        the new files are recorded
        """
        assert self.__corpus_versions, "Expected that corpus versions have been generated"

        version_ids = list(self.__corpus_versions.keys())

        n = 1
        # start from beginning
        for version_id in version_ids:
            this_version = self.__corpus_versions[version_id]
            #logging.debug(f"This version is {this_version['id']}.")


            if n != len(version_ids):
                # this should be the next version
                #logging.debug(n)
                next_version_id = version_ids[n:n+1][0]
                #logging.debug(next_version_id)
                next_version = self.__corpus_versions[next_version_id]

                #logging.debug(f"Next version is {next_version['id']}")

            else:
                logging.debug("This is the last version.")
                break
            
            # test if these are consecutive versions
            if this_version["running_number"] + 1 != next_version["running_number"]:
                logging.warning("These are not consecutive versions. Why?")
            
            if next_version["document_count"] > this_version["document_count"]:
                diff = next_version["document_count"] - this_version["document_count"]
                logging.debug(f"The next version has {str(diff)} more plays than this version.")

                # write the document count then
                self.__corpus_versions[next_version_id]["new_documents_count"] = diff

                new_plays = self.compare_files_of_versions(this_version["id"], next_version["id"])
                logging.debug("New plays in the next version: ")
                logging.debug(new_plays)
                self.__corpus_versions[next_version_id]["new_playnames"] = new_plays
            
            else:
                #logging.debug("The next version has the same number of plays.")
                pass

            n = n + 1
    
    def get_corpus_version_adding_play(self, playname: str = None):
        """Get the corpus version a play is added.
        This would allow to get the information since when a play is available in the corpus.
        
        If the file has been explicitly added in a version the method will return the data of this version.
        If the file exists, the method will return True only; it will return False if there is no such filename
        """
        
        assert self.__corpus_versions, "Expect that corpus versions are generated"
        # also that they have the info which plays are added new
        assert type(playname) == str, "Expecting a playname as a string"

        found_in_version = None
        found_at_all = False

        for key in self.__corpus_versions.keys():
            if "new_playnames" in self.__corpus_versions[key]:
                # new plays are added with this version, check if the playname is included
                if playname in self.__corpus_versions[key]["new_playnames"]:
                    found_in_version = self.__corpus_versions[key]
                    logging.debug(f"Found in version {found_in_version['id']}")
                    found_at_all = True
                    return found_in_version
        
        if found_in_version is None:
            logging.debug(f"Could not find {playname} in newly added plays. Could be there from the beginning.")
            
            logging.debug("Checking all versions...")

            for key in self.__corpus_versions.keys():
                if playname in self.__corpus_versions[key]["playnames"]:
                    logging.debug(f"Found filename in the list of filenames in version {key} for the first time.")
                    found_at_all = True
                    break
        
        if found_at_all == True:
            logging.debug(f"Could find the file {playname}, but it was not added explicitly in a version. It might have been part of the corpus from the start.")
            # This is a very peculiar behaviour...
            return True
        else:
            logging.warning(f"Could not find a file with filename {playname} at all.")
            return False

    def __fetch_data_folder_objects(self):
        """This fetches and stores the data folder objects
        Store them in self.__data_folder_objects = None
        """
        assert self.__corpus_versions, "Expected that corpus versions have been created"
        
        # Initialize the data folder as empty dictionary
        self.__data_folder_objects = dict()

        for key in self.__corpus_versions.keys():
            if "data_folder_github_url" in self.__corpus_versions[key]:
                # iterate over the versions and get the api link to the tree object
                github_data_folder_api_url = self.__corpus_versions[key]["data_folder_github_url"]
                self.__data_folder_objects[key] = self.api_get(url=github_data_folder_api_url)
                logging.debug(f"Stored data folder object from {github_data_folder_api_url} of corpus version {key}.")
            else:
                logging.warning(f"Retrieving data folder url of version {key} failed.")
        
        return True
    
    def get_data_folder_objects(self):
        """Get the Github Data folder Objects containing the tree info for corpus versions"""

        if self.__data_folder_objects is not None:
            return self.__data_folder_objects
        else:
            logging.debug("Fetching data from GitHub...")
            self.__fetch_data_folder_objects()
    

    def store_data_folder_objects(self, 
                     folder_name:str = "export",
                     file_name: str = None,
                     ensure_ascii: bool = False):
        """Save the downloaded data folder objects"""
        if self.__data_folder_objects is None:
            logging.critical("No data folder objects created. Aborting.")
            raise Exception("No data folder objects created.")
        
        if file_name is None:
            file_name = f"{self.__repository_name}_data_folder_objects"
    

        with open(f"{folder_name}/{file_name}.json", "w", encoding='utf8') as f:
            f.write(json.dumps(self.__data_folder_objects, ensure_ascii=ensure_ascii))
    
    def import_data_folder_objects(self,
                       file:str = None):
        """Import saved data folder objects"""
        with open(file, "r") as f:
            data = json.load(f)
        
        self.__data_folder_objects = data
        logging.info(f"Imported data folder objects from {file}.")

    def add_sum_of_document_sizes_to_versions(self):
        """Add the sum of the sizes of all documents in the data folder to the version
        
        Unit should be bytes.
        """
        assert self.__corpus_versions, "Expect that corpus versions are generated"
        assert self.__data_folder_objects, "Expect that data folder objects have been downloaded"
        
        for version_key in self.__corpus_versions.keys():
            
            sum_documents_size = 0
            data_folder_object = self.__data_folder_objects[version_key]
            files = data_folder_object["tree"]

            for file in files:
                sum_documents_size = sum_documents_size + file["size"]
        
            self.__corpus_versions[version_key]["document_sizes_sum"] = sum_documents_size

        return True
    
    def plot_document_sizes_sum_in_corpus_versions(self, 
                                          xlabel:str = None, 
                                          ylabel:str = None,
                                          title:str = None):
        """Plot the sum of document sizes in the corpus over time"""
        df = self.get_corpus_versions_as_df(columns=["date_from","document_sizes_sum"]).set_index("date_from")
        if xlabel:
            plt.xlabel(xlabel)
        else:
            plt.xlabel("Year")

        if ylabel:
            plt.ylabel(ylabel)
        else:
            plt.ylabel("Sum of Document Sizes [Bytes]")

        if title:
            plt.title(title)

        plt.plot(df["document_sizes_sum"])
    
    def get_github_commit_url_of_version(self, version:str = None):
        """Generates a link to see the commit in the Github GUI. Allows to load the diff(s)"""
        return f"https://github.com/{self.__repository_owner}/{self.__repository_name}/commit/{version}"
    
    def get_document_file_data_in_version(self, version:str = None, name:str = None):
        """Returns the file object from the tree object of a single commit
        Args:
            name (str): Name of the file/playname without .xml extension!
            version (str): commit sha/version id
        """
        data_folder_tree_of_version = self.__data_folder_objects[version]["tree"]
        file_data_in_list = list(filter(lambda item: item["path"] == f"{name}.xml", data_folder_tree_of_version))
        if len(file_data_in_list) == 1:
            return file_data_in_list[0]
        else:
            logging.debug(f"File {name} not found in this version.")
            return None

    def get_sizes_of_single_play_as_df(self, name:str = None, no_value:int = None):
        """Get the file sizes of single play from all versions
        
        Args:
            no_value (int, optional): Can set what happens if there is no value, i.e. no file. Defaults to None
        
        """
        data = dict(
            version=[],
            date_from=[],
            size=[]
        )
        
        for key in self.__corpus_versions.keys():
            
            data["version"].append(key)
            data["date_from"].append(self.__corpus_versions[key]["date_from"])
            if "playnames" not in self.__corpus_versions[key]:
                logging.debug(key)
            if name in self.__corpus_versions[key]["playnames"]:
                # get the data of a single file from the tree folder (data_folder_objects)
                file_data = self.get_document_file_data_in_version(name=name, version=key)
                data["size"].append(file_data["size"])
            else:
                data["size"].append(no_value)
        
        df = pd.DataFrame(data)
        df["date_from"] = pd.to_datetime(df["date_from"])

        return df
    
    def plot_document_size_in_corpus_versions(self,
                                                name:str = None, 
                                                xlabel:str = None, 
                                                ylabel:str = None,
                                                title:str = None,
                                                no_value:int = None):
        """Plot the size of a single document in the corpus over time
        Args:
            name (str): Name of the play/filename without .xml extension
            xlablel (str): Label of the x-axis
            xlablel (str): Label of the y-axis
            no_value (int, optional): Set empty values, good options are None (default) or 0.
        """
        df = self.get_sizes_of_single_play_as_df(name=name, no_value=no_value).set_index("date_from")
        
        if xlabel:
            plt.xlabel(xlabel)
        else:
            plt.xlabel("Year")

        if ylabel:
            plt.ylabel(ylabel)
        else:
            plt.ylabel("File Size [Bytes]")

        if title:
            plt.title(title)
        else:
            plt.title(f"Development of File Size of {name}")

        plt.plot(df["size"])

    def get_size_changes_of_document(self, name:str = None):
        """Get version IDs in which the file size of a given file changes
        This might mean that there are edits on this file
        TODO: implement a version of this that compares the current size to the size of the file in the prev version"""
        # start with 0 size
        size_changes = []
        size = 0
        for key in self.__corpus_versions.keys():
            file_data = self.get_document_file_data_in_version(version=key,name=name)
            
            if file_data is not None:
                this_version_size = file_data["size"]
                if this_version_size != size:
                    logging.debug(file_data)
                    logging.debug(f"was size {size}")
                    logging.debug(f"this size {this_version_size}")
                    data = dict(
                        version=key,
                        size=this_version_size,
                        link=self.get_github_commit_url_of_version(version=key)
                    )
                    size_changes.append(data)
                    size = this_version_size
        
        return size_changes
    
    def get_document_version_github_metadata(self, name:str = None, 
                                             version:str = None,
                                             exclude_content:bool = True):
        """Retrieves the metadata about a single versioned file from GitHub
        
        Args:
            name (str, required): Filename/playname without file extension
            version (str, required): ID of a version (=commit sha)
            exclude_content (bool, optional): Flag to remove the base64 encoded content of the frile from the returned object
        """
        url = f"https://api.github.com/repos/{self.__repository_owner}/{self.__repository_name}/contents/{self.__corpus_versions[version]['data_folder_name']}%2F{name}.xml?ref={version}"
        data = self.api_get(url=url)
        if exclude_content is True:
            data.pop("content")
            data.pop("encoding")
        return data 

    def get_detailed_commits(self, 
                             force_download=False,
                             only_download=False):
        """Return (and download) the detailed commits from GitHub"""
        if self.__commits_detailed and force_download == False:
            return self.__commits_detailed
        else:
            logging.debug("Fetching detailed commits from GitHub")
            assert self.__commits, "Expect that commits have already beend downloaded."
            # This is not ideal, I rely on having the commits already available
            self.__commits_detailed = []
            for commit in self.__commits:
                sha = commit["sha"]
                url = f"https://api.github.com/repos/{self.__repository_owner}/{self.__repository_name}/commits/{sha}"
                
                # Here I must handle it as it is done with get commits, i.e. get the whole response object
                
                paged_results = []
                has_pages_left = True 
                while has_pages_left is True:
                    logging.debug(f"Will get results from {url}")
                    r = self.api_get(url=url, return_response_object=True)
                    
                    try:
                        link_headers = self.__parse_link_headers(r.headers)
                    except:
                        link_headers = None
                    
                    if link_headers == None:
                        has_pages_left = False
                    elif "next" not in link_headers:
                        # this is the exit condition
                        has_pages_left = False

                    parsed_commits = json.loads(r.text)
                    paged_results.append(parsed_commits)

                    if link_headers == None:
                        logging.debug("Nothing more to get")
                        break
                    elif "next" in link_headers:
                        url=link_headers["next"]
                    else:
                        logging.debug("Nothing more to get")
                        break
                   
                if len(paged_results) == 1:
                    self.__commits_detailed.append(paged_results[0])
                else:
                    prepared_commit_object = paged_results[0]
                    for page in paged_results[1:]:
                       for file in page["files"]:
                            prepared_commit_object["files"].append(file)
                    self.__commits_detailed.append(prepared_commit_object)
                
                logging.debug(f"Downloaded {sha}.")
                # Here the problem is, that the results are paged
            
            if only_download == True:
                logging.debug("Done downloading detailed commits.")
                return True
            else:
                return self.__commits_detailed
    
    def store_detailed_commits(self, 
                     folder_name:str = "export",
                     file_name: str = None):
        """Save the downloaded detailed commits"""
        if self.__commits_detailed is None:
            logging.critical("No detailed commits downloaded. Aborting.")
            raise Exception("No detailed commits downloaded.")
        
        if file_name is None:
            file_name = f"{self.__repository_name}_commits_detailed"
    

        with open(f"{folder_name}/{file_name}.json", "w") as f:
            f.write(json.dumps(self.__commits_detailed))
    
    def import_detailed_commits(self,
                       file:str = None):
        """Import saved detailed commits"""
        with open(file, "r") as f:
            data = json.load(f)
        
        self.__commits_detailed = data
        logging.info(f"Imported detailed commits from {file}.")


    def enrich_corpus_versions_with_detailed_commits(self):
        """Adds the information of detailed commits to the versions
        
        """
        assert self.__commits_detailed, "Expected detailed commits to be available."
        
        for commit in self.__commits_detailed:
            commit_id = commit["sha"]
            
            if "files" in commit:
                # these are the files like corpus.xml, ... others, like css
                non_document_files_affected_count = 0
                non_document_files_affected = []

                #document files
                # only count if the filename split by .xml is in the version[playnames]; it could be other files as well

                documents_affected_count = 0
                documents_modified_count = 0
                documents_removed_count = 0
                documents_added_count = 0
                documents_renamed_count = 0

                document_modified_playnames = []

                for file in commit["files"]:
                    file_path = file["filename"]
                    # this includes the data_folder_name
                    #logging.debug(f"filepath: {file_path}")
                    #if f"{self.__corpus_versions[commit_id]['data_folder_name']}/" and ".xml" in file_path:
                    if f"{self.__corpus_versions[commit_id]['data_folder_name']}/" in file_path:
                        playname = file_path.split(f"{self.__corpus_versions[commit_id]['data_folder_name']}/")[1].replace(".xml", "")
                        #logging.debug({playname})
                        if playname in self.__corpus_versions[commit_id]["playnames"]:
                            # this is a relevant file
                            documents_affected_count = documents_affected_count + 1
                            if file["status"] == "modified":
                                documents_modified_count = documents_modified_count + 1
                                document_modified_playnames.append(playname)
                            elif file["status"] == "added":
                                documents_added_count = documents_added_count + 1
                            elif file["status"] == "renamed":
                                documents_renamed_count = documents_renamed_count + 1
                                #logging.debug(f"renamed {playname}")
                            elif file["status"] == "removed":
                                documents_removed_count = documents_removed_count + 1

                            else:
                                raise Exception(f"Unexpected status: {file['status']}")

                    else:
                        non_document_files_affected_count = non_document_files_affected_count + 1
                        #logging.debug("Found non-play document affected by change")
                        non_document_files_affected.append(file_path)
                        if file["status"] not in ["added","renamed", "modified", "removed"]:
                            raise Exception(f"{file['status']} not forseen.")
            
            if documents_affected_count != 0:
                self.__corpus_versions[commit_id]["documents_affected_count"] = documents_affected_count
            if documents_modified_count != 0:
                self.__corpus_versions[commit_id]["documents_modified_count"] = documents_modified_count
            if document_modified_playnames != []:
                self.__corpus_versions[commit_id]["document_modified_playnames"] = document_modified_playnames
            if documents_added_count != 0:
                self.__corpus_versions[commit_id]["documents_added_count"] = documents_added_count
            if documents_renamed_count != 0:
                self.__corpus_versions[commit_id]["documents_renamed_count"] = documents_renamed_count
            if documents_removed_count != 0:
                self.__corpus_versions[commit_id]["documents_removed_count"] = documents_removed_count
            if non_document_files_affected_count != 0:
                self.__corpus_versions[commit_id]["non_document_files_affected_count"] = non_document_files_affected_count
            if non_document_files_affected != []: 
                self.__corpus_versions[commit_id]["non_document_files_affected"] = non_document_files_affected
        
        return True
    
    def get_corpus_versions_modifying_document(self, name:str = None):
        """Get some data of the versions that modify a document
        
        Args:
            name (str, required): Name/Identfier playname/filename (without extension) of a document
        """

        assert self.__corpus_versions, "Experct corpus versions to be available"
        
        results = []
        
        for key in self.__corpus_versions.keys():
            if "document_modified_playnames" in self.__corpus_versions[key]:
                if name in self.__corpus_versions[key]["document_modified_playnames"]:
                    version_info = dict(
                        version=key,
                        date_from=self.__corpus_versions[key]["date_from"],
                        link=self.get_github_commit_url_of_version(version=key)
                    )
                    results.append(version_info)

        return results
        

    def get_detailed_commit(self, sha:str = None):
        """Get a single detailed commit"""
        data = list(filter(lambda item: item["sha"] == sha, self.__commits_detailed))[0]
        return data
    
    def get_corpus_version_fields(self):
        """List the available data fields on corpus versions; these are also the columns when requesting the data frame"""
        return self.__corpus_version_data_fields
    
    def get_latest_corpus_contents_from_api(self, 
                                            api_base:str = "https://dracor.org/api/v1/", 
                                            corpus_name:str = None):
        """Returns the parsed content of the list-corpus-content endpoint
        Args:
            api_base (str, optional): "Base URL of the (DraCor) API. Defaults to https://dracor.org/api/v1/
            corpus_name (str, optional): Identfier "corpusname" as used in the endpoint. Will be guessed from the repo-name if not supplied.
        """
        if self.__latest_corpus_contents_from_api is not None:
            return self.__latest_corpus_contents_from_api
        
        else:
            logging.debug("Need to fetch latest corpus contents from API")
            if corpus_name is None:
                # guess it
                corpus_name = self.__repository_name.lower().replace("dracor","")
                logging.debug(f"Guessed corpus name {corpus_name}")

            url = f"{api_base}corpora/{corpus_name}"
            r = requests.get(url=url)
            if r.status_code == 200:
                self.__latest_corpus_contents_from_api = json.loads(r.text)
                return self.__latest_corpus_contents_from_api
            else:
                logging.warning(f"Fetching latest listing of corpus contents via {url} failed. Server returned status code {str(r.status_code)}.")
                return None
    
    def __generate_source_key_from_name(self, source_name):
        return source_name.lower().replace(" ", "_").replace(":","_")


    def get_source_distribution_of_corpus_version(self, version:str = None):
        """Returns the number of plays taken from a source. This uses the value source.name from the response of
         the latest version of DraCor (as available via the endpoint /corpora/corpusname). So, it does not download and "look" into each file! If this is not stable across versions, the result is wrong. 
         
        API Feature: play_digital_source_name – https://lod.dracor.org/api-ontology/play_digital_source_name 
        Name of the digital source of a play. Normally it is the name of the repository or project that provides a digital version of the play, e.g. 'Google Books', 'Wikisource', 'TextGrid Repository'.
        """

        sources = dict()

        # get the data to use
        recent_api_plays_metadata = self.get_latest_corpus_contents_from_api()["plays"]

        for playname in self.__corpus_versions[version]["playnames"]:
            recent_api_play_data_list = list(filter(lambda play: play["name"] == playname, recent_api_plays_metadata))
            if len(recent_api_play_data_list) == 1:
                recent_play_data = recent_api_play_data_list[0]
                source_name = recent_play_data["source"]["name"]

                source_key = self.__generate_source_key_from_name(source_name)
                if source_key not in sources:
                    # first time this source is detected
                    sources[source_key] = dict(
                        source_name=source_name,
                        plays_count=1
                    )
                else:
                    sources[source_key]["plays_count"] = sources[source_key]["plays_count"] + 1
        
        result = dict(
            version=version,
            date_from=self.__corpus_versions[version]["date_from"],
            document_count=self.__corpus_versions[version]["document_count"],
            distinct_sources_count=len(sources.keys()),
            sources=sources
        )

        return result
    
    def get_source_distribution_of_corpus_version_as_df(self, version:str = None):
        """Returns a pandas data frame of the counts of plays per source"""
        source_distribution_data = self.get_source_distribution_of_corpus_version(version = version)
        data = dict(
            source_key=[],
            source_name=[],
            play_count=[]
        )
        for source_key in source_distribution_data["sources"].keys():
            data["source_name"].append(source_distribution_data["sources"][source_key]["source_name"])
            data["source_key"].append(source_key)
            data["play_count"].append(source_distribution_data["sources"][source_key]["plays_count"])
        

        df = pd.DataFrame(data=data)
        df = df.set_index("source_key")
        df = df.sort_values("play_count", ascending=False)
        return df


    def plot_source_distribution_of_corpus_version(self, version: str = None):
        """Plot the distribution of sources as pie chart"""
        df = self.get_source_distribution_of_corpus_version_as_df(version=version)
        
        df.set_index("source_name")
        df.plot(kind='pie', y="play_count", autopct="%1.0f%%").legend(
            fontsize='small',
            bbox_to_anchor=(1.0, 1.0))
    
    def __generate_all_source_distributions(self):
        """Generate source distributions for all versions"""
        
        self.__source_distributions = []
        for version in self.__corpus_versions.keys():
            logging.debug(f"Generating source distributions of {version}.")
            data = self.get_source_distribution_of_corpus_version(version=version)
            self.__source_distributions.append(data)
    
    def __generate_distinct_sources(self, based_on: str = "data"):
        """Generate information about distinct sources
        this is either done based on the source distributions (more exact), on based on the latest
        data in the production API

        Args:
            based_on (str, optional): Generate the sources based on the source distributions or the latest API data
                "api" - fetch from api, "data" (default value): calculate based on source distributions

        """
        distinct_sources = dict()

        if based_on == "api":
            latest_api_data = self.get_latest_corpus_contents_from_api()
            plays = latest_api_data["plays"]
            for play in plays:
                if play["source"]["name"] not in distinct_sources:
                    source_key = self.__generate_source_key_from_name(play["source"]["name"])
                    distinct_sources[source_key] = dict(
                        key=source_key,
                        name=play["source"]["name"],
                        rank=None
                    )
        elif based_on == "data":
            if self.__source_distributions is None:
                self.__generate_all_source_distributions()
            
            all_source_keys = []
        
            for source_distribution in self.__source_distributions:
                source_keys = list(source_distribution["sources"].keys())
                for key in source_keys:
                    all_source_keys.append(key)
        
            distinct_keys = set(all_source_keys)
            for key in distinct_keys:
                distinct_sources[source_key] = dict(
                        key=source_key,
                        name=None,
                        rank=None
                    )            

        else: 
            raise Exception(f"{based_on} is not a valid value of param 'based_on': use 'api' or 'data'.")
        
        self.__sources = distinct_sources

        # should also add the ranks and order
        self.__add_ranks_to_sources()
    
    def get_distinct_sources(self):
        """Returns information about the sources"""
        if self.__sources is not None:
            return self.__sources
        else:
            self.__generate_distinct_sources()
            return self.__sources

    def get_latest_corpus_version(self):
        """Shortcut to get the latest corpus version"""
        if self.__corpus_versions is not None:
            latest_key = list(self.__corpus_versions.keys())[-1:][0]
            return self.__corpus_versions[latest_key]

    def __add_ranks_to_sources(self, based_on_version:str = None):
        """Add ranks to sources based on the number of plays in a certain corpus version
        For the time being the latest version will be used
        """
        if based_on_version is not None:
            raise Exception("Not yet implemented. Try w/o parameter 'based on version'.")
        
        version = self.get_latest_corpus_version()
        source_distribution = self.get_source_distribution_of_corpus_version(version["id"])

        sources_as_list = []
        for key in source_distribution["sources"].keys():
            sources_as_list.append(source_distribution["sources"][key])

        sources_as_sorted_list = sorted(sources_as_list, key=lambda x: x["plays_count"])
        sources_as_sorted_list.reverse()
        logging.debug("Sorted List:")
        logging.debug(sources_as_sorted_list)
        
        

        new_sources = dict()

        n = 1
        for item in sources_as_sorted_list:
            key = self.__generate_source_key_from_name(item["source_name"])
            reorder_this_item = self.__sources[key]
            reorder_this_item["rank"] = n
            new_sources[key] = reorder_this_item
            n = n + 1
            
        self.__sources = new_sources
        


    def get_source_distribution_of_corpus_versions_as_df(self):
        """Plot source distribution over time"""
        if self.__source_distributions is None:
            self.__generate_all_source_distributions()
        
        data = dict(
            version=[],
            date_from=[],
            document_count=[],
            distinct_sources_count = []
        )

        if self.__sources is None:
            self.__generate_distinct_sources(based_on="api")

        for source_key in self.__sources.keys():
            data[source_key] = []

        for source_distribution in self.__source_distributions:
            data["version"].append(source_distribution["version"])
            data["date_from"].append(source_distribution["date_from"])
            data["document_count"].append(source_distribution["document_count"])
            data["distinct_sources_count"].append(source_distribution["distinct_sources_count"])

            for source_key in self.__sources.keys():
                if source_key in source_distribution["sources"]:
                    data[source_key].append(source_distribution["sources"][source_key]["plays_count"])
                else:
                    data[source_key].append(0)
        
        df = pd.DataFrame(data=data)
        df["date_from"] = pd.to_datetime(df["date_from"])
        return df

    def plot_source_distribution_of_corpus_versions(self):
        df = self.get_source_distribution_of_corpus_versions_as_df()
        
        columns = ["date_from"]
        for source_key in self.__sources.keys():
            columns.append(source_key)
        
        plot_df = df[columns]
        plot_df = plot_df.set_index("date_from")

        plot_df.plot.area().legend(
            fontsize='small',
            bbox_to_anchor=(1.0, 1.0))

    def get_years_of_corpus_version_as_df(self, version:str = None, non_numbers_to_nan=True):
        """Get years of a certain type of plays in corpus version
        Types of year are:
        - yearNormalized 
        - yearPrinted
        - yearWritten 
        - yearPremiered

        Args:
            version (str, required): Version number/id/commit id
            year_type (str, optional): Type of year: 'printed', 'written', 'premiered; defaults to 'normalized'
            non_numbers_to_nan (bool, optional): Turn all non numbers in years to NaN
        """
        year_keys = ["yearNormalized", "yearPrinted",  "yearWritten", "yearPremiered"]
        data = dict(
            playname=[]
        )
        
        for year_key in year_keys:
            data[year_key] = []

        api_data = self.get_latest_corpus_contents_from_api()

        for playname in self.__corpus_versions[version]["playnames"]:
            
            play_api_data_candidates = list(filter(lambda play: play["name"] == playname, api_data["plays"]))
            if len(play_api_data_candidates) == 1:
                play_api_data = play_api_data_candidates[0]
            else:
                # TODO: This needs to be fixed! the problem are renamed files
                #logging.warning(f"Can not find {playname} in latest API data.")
                play_api_data = None
            
            # TODO: here there is a problem if a play is renamed!
            data["playname"].append(playname)
            for year_key in year_keys:
                if play_api_data is None:
                    data[year_key].append(None)
                else:
                    data[year_key].append(play_api_data[year_key])
        
        df = pd.DataFrame(data).set_index("playname")
        #convert columns to numeric – does not work
        if non_numbers_to_nan is True:
            for key in year_keys:
                df[key] = pd.to_numeric(df[key], errors='coerce')
        return df

    def plot_years_of_corpus_version(self, version:str = None, year_type:str = "normalized"):
        """Create a boxplot of the years of a corpus version
        
        Plots the years (by type, printed, normalized, written, premiered) of plays as a boxplot
        """
        assert version is not None, "Version ID must be supplied."

        df = self.get_years_of_corpus_version_as_df(version=version)

        column_name = f"year{year_type.capitalize()}"

        df.boxplot(column=column_name)


    def get_min_max_years_of_corpus_version(self, version:str = None, year_type:str = "normalized") -> dict:
        """Get the min and max values of all years of a certain type in a corpus version
        Gets the information about the dates from the DraCor API /corpora/{corpusname} endpoint
        
        Types of year are:
        - yearNormalized ("normalized")
        - yearPrinted ("printed")
        - yearWritten ("written")
        - yearPremiered ("premiered")

        Args:
            version (str, required): Version number/id/commit id
            year_type (str, optional): Type of year: 'printed', 'written', 'premiered; defaults to 'normalized'
        """
        assert version is not None, "Expects a version id."
        
        df = self.get_years_of_corpus_version_as_df(version=version)

        column_name = f"year{year_type.capitalize()}"

        return df[column_name].min(), df[column_name].max() 
    
    def get_min_max_years_of_corpus_versions_as_df(self, year_type:str = "normalized"):
        """Returns all min max years of all corpus versions"""
        
        year_column_name = f"year{year_type.capitalize()}"

        data = dict(
            version=[],
            date_from=[],
            year_min = [],
            year_max=[]
        )
        
        
        for key in self.__corpus_versions.keys():
            data["version"].append(key)
            data["date_from"].append(self.__corpus_versions[key]["date_from"])
            
            year_vals = self.get_min_max_years_of_corpus_version(version=key, year_type=year_type)
            data["year_min"].append(year_vals[0])
            data["year_max"].append(year_vals[1])
        
        df = pd.DataFrame(data=data)
        df["date_from"] = pd.to_datetime(df["date_from"])

        return df
    
    def plot_min_max_years_of_corpus_versions(self):
        """Plot years"""
        df = self.get_min_max_years_of_corpus_versions_as_df().set_index("date_from")
        
        df.plot()

    def __fetch_and_prepare_analysis_data(self):
        """Download the data needed for the analysis from GitHub and prepare the versions
        This might take a long time depending on the number of commits in a repository"""

        logging.info(f"Downloading data from GitHub and preparing for analysis. Depending on the number of commits this will take a long time.")

        #Create a folder
        if not os.path.exists("tmp"):
            os.makedirs("tmp")

        # There is a certain order of the download and enrichment-steps (because of the chaotic way the module came into being)
        # get the commits overview, these is the basis for the first set of versions
        self.get_commits(force_download=True)
        try:
            self.store_commits(folder_name="tmp")
            logging.info("Step 1: Downloaded and stored commits.")
        except:
            pass

        self.__data_download_at = datetime.now()
        
        # create the intial versions based on the commits
        self.__transform_commits_to_versions()
        logging.info("Step 2: Generated initial versions based on commits. Enriching ...")
        # by then self.__corpus_versions should be available
        # store it, can overwrite after enriching
        try:
            self.store_corpus_versions(folder_name="tmp")
            logging.info("Downloaded and stored initial corpus versions.")
        except:
            pass


        # this might add information which files are in a version
        # this is not ideal, it failed at some point
        self.add_files_to_versions()
        logging.info("Step 3: Added files to versions.")
        # There is a problem, because in the early version, for example, of GerDraCor
        # the data folder is not "tei" but "data"

        # This adds the information when a play was added to a version
        self.add_new_play_info_to_corpus_versions()
        logging.info("Step 4: Added information when a play was first added to corpus.")

        # Download the data folder objects; these represent the files of a commit
        # needed for the information about the sizes of files in a corpus
        self.__fetch_data_folder_objects()
        try:
            self.store_data_folder_objects(folder_name="tmp")
            logging.info("Step 5: Downloaded and stored data folder objects.")
        except:
            pass

        # adds the cumulative sum of filesizes to versions
        self.add_sum_of_document_sizes_to_versions()
        logging.info("Step 6: Added sum of document sizes to versions.")

        # get the detailed commit
        self.get_detailed_commits(force_download=True)
        try:
            self.store_detailed_commits(folder_name="tmp")
            logging.info("Step 7: Downloaded and stored detailed commits. Enriching versions...")
        except:
            pass

        # based on the above, do an enrichment. This adds the information what has happend to a file in 
        # a version, e.g. modified n files...
        self.enrich_corpus_versions_with_detailed_commits()
        logging.info("Step 8: Enriched versions with information from detailed commits.")

        try:
            self.store_corpus_versions(folder_name="tmp")
            logging.info("Stored enriched corpus versions.")
        except:
            pass

        # this can also be cached: the info about plays taken from the latest version in DraCor
        #self.get_latest_corpus_contents_from_api()

        # generate the distribution of sources
        #self.__generate_all_source_distributions()

        logging.info("Done downloading and preparing data for analysis.")

    def get_ids_of_corpus_versions_renaming_documents(self):
        """Get a list of commit ids of corpus versions that rename one or more plays"""
        ids = []
        for key in self.__corpus_versions.keys():
            if "documents_renamed_count" in self.__corpus_versions[key]:
                ids.append(key)
        return ids
    
    def get_ids_of_corpus_versions_modifying_all_documents(self):
        """Get a list of ids of corpus versions that modify all documents
        Compares the values of the fields "documents_modified_count" and document_count. If they match all documents have been modified
        in this version
        """
        ids = []
        for key in self.__corpus_versions.keys():
            if "documents_modified_count" in self.__corpus_versions[key]:
                if self.__corpus_versions[key]["documents_modified_count"] == self.__corpus_versions[key]["document_count"]:
                    ids.append(key)  
        return ids


    def get_renamed_files(self, 
                          exclude_versions:list = []):
        """Get files that were renamed
        
        Args:
            exclude_versions (list, optional): Version numbers/commit ids to exclude
        """
        renamed = []
        for detailed_commit in self.__commits_detailed:
            # don't do this if a version is filtered out; maybe I don't want to see the batch renamings of all files
            if detailed_commit["sha"] not in exclude_versions:
                for file in detailed_commit["files"]:
                    if file["status"] == "renamed":
                        rename_info = dict(
                            version=detailed_commit["sha"],
                            previous_filename=file["previous_filename"],
                            new_filename=file["filename"]  
                        )
                        renamed.append(rename_info)
        return renamed
    
    def get_corpus_version_ids_in_date_range(self, date_start:str = None, date_end:str = None):
        """Get ids of corpus versions in date range"""
        start = datetime.fromisoformat(date_start)
        end = datetime.fromisoformat(date_end)

        result_version_ids = []

        for version_id in self.__corpus_versions.keys():
            version_date = datetime.fromisoformat(self.__corpus_versions[version_id]["date_from"]).replace(tzinfo=None)
            if start <= version_date and end >= version_date:
                result_version_ids.append(version_id)

        return result_version_ids
    
    def get_plays_in_corpus_versions_in_date_range(self, date_start:str = None, date_end:str = None):
        """Get play names of plays in corpus versions that fall within a time range"""
        corpus_version_ids = self.get_corpus_version_ids_in_date_range(date_start=date_start, date_end=date_end)

        unique_playnames = []

        for version_id in corpus_version_ids:
            playnames = self.__corpus_versions[version_id]["playnames"]
            for playname in playnames:
                if playname not in unique_playnames:
                    unique_playnames.append(playname)
        
        return unique_playnames


    def get_years_of_plays_in_corpus_version_in_date_range_as_df(self, date_start:str = None, date_end:str = None, non_numbers_to_nan=True):
        """Get years plays in a time span
        Types of year are:
        - yearNormalized 
        - yearPrinted
        - yearWritten 
        - yearPremiered

        Args:
            date_start(str): Start date in iso format
            date_end(str): End date in iso format
            year_type (str, optional): Type of year: 'printed', 'written', 'premiered; defaults to 'normalized'
            non_numbers_to_nan (bool, optional): Turn all non numbers in years to NaN
        """
        year_keys = ["yearNormalized", "yearPrinted",  "yearWritten", "yearPremiered"]
        data = dict(
            playname=[]
        )
        
        for year_key in year_keys:
            data[year_key] = []

        api_data = self.get_latest_corpus_contents_from_api()

        for playname in self.get_plays_in_corpus_versions_in_date_range(date_start=date_start, date_end=date_end):
            
            play_api_data_candidates = list(filter(lambda play: play["name"] == playname, api_data["plays"]))
            if len(play_api_data_candidates) == 1:
                play_api_data = play_api_data_candidates[0]
            else:
                # TODO: This needs to be fixed! the problem are renamed files
                #logging.warning(f"Can not find {playname} in latest API data.")
                play_api_data = None
            
            # TODO: here there is a problem if a play is renamed!
            data["playname"].append(playname)
            for year_key in year_keys:
                if play_api_data is None:
                    data[year_key].append(None)
                else:
                    data[year_key].append(play_api_data[year_key])
        
        df = pd.DataFrame(data).set_index("playname")
        #convert columns to numeric – does not work
        if non_numbers_to_nan is True:
            for key in year_keys:
                df[key] = pd.to_numeric(df[key], errors='coerce')
        return df

                    
