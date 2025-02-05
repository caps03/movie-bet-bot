from __future__ import annotations

import copy
from datetime import datetime
from typing import Dict, List, Set, Union

import tmdbsimple as tmdb
import yaml
from bs4 import BeautifulSoup

from movie_bet_bot.utils import constants
from movie_bet_bot.utils.fetchers import fetch_page_body_from_url
from movie_bet_bot.utils.images import html_to_image
from movie_bet_bot.utils.utils import map_place
from movie_bet_bot.models.logger.logger import print


class Film:

    # film tile
    title: str

    # film Letterboxd URL
    url: str

    # film runtime
    runtime: int = -1

    # film TMDB poster URL
    poster_url: str = ""

    # film's rating given by user in starts
    _rating: str = ""

    def __init__(
        self,
        title: str,
        url: str,
        runtime: int = -1,
        poster_url: str = "",
    ) -> None:
        self.title = title
        self.url = url
        self.runtime = runtime
        self.poster_url = poster_url

    def to_dict(self) -> Dict[str, str]:
        """
        Create a dictionary representation of this Film object.

        :return: dictionary representation of this Film object
        """
        return {
            "title": self.title,
            "url": self.url,
            "runtime": self.runtime,
            "poster_url": self.poster_url,
        }

    @property
    def rating(self) -> str:
        """
        Get rating.

        :return: film's rating in stars
        """
        return self._rating

    @rating.setter
    def rating(self, r: str) -> None:
        """
        Set rating.

        :param r: rating in stars to give the film
        """
        self._rating = r

    def __repr__(self) -> str:
        return (
            f"Film(title='{self.title}',url='{self.url}',"
            f"runtime={self.runtime},poster_url='{self.poster_url}')"
        )

    def __eq__(self, __o: Film) -> bool:
        return self.title == __o.title and self.url == __o.url

    def __hash__(self):
        return hash(tuple((self.title, self.url)))


class FilmList:

    # list's Letterboxd URL
    url: str

    # set of films contained in this list
    films: Set[Film]

    def __init__(self, url: str, films: Set[Film] = set()) -> None:
        self.url = url
        self.films = films

    @staticmethod
    async def from_url(url: str, get_film_details: bool = True) -> FilmList:
        """
        Create a list from a Letterboxd URL.

        :param url: Letterboxd URL of the list to create
        :param get_film_details: if details from TMDB should be retrieved
        :return: FilmList object
        """
        films: Set[Film] = set()
        page_number: int = 1
        page_url: str = url + "page/"
        while True:
            print(f"Fetching film list page_url {page_url}{str(page_number)}/")
            # get raw list page body
            list_page = await fetch_page_body_from_url(page_url + str(page_number) + "/")
            # get all li nodes with the film class name
            list_result = list_page.find_all("li", class_=constants.FILM_CLASS_NAME)
            li: BeautifulSoup
            for li in list_result:
                # get film title, year, and url from the li node
                film_title = li.a.text
                film_year = li.find_all("small", {"class": "metadata"})[0].a.text.strip()
                film_url = constants.LB_URL_ROOT + li.a["href"]
                film = Film(film_title, film_url)
                # try to get rating if one is given, pass otherwise
                try:
                    film.rating = li.find_all("span", {"class": "rating"})[0].text.strip()
                except (AttributeError, IndexError):
                    pass
                if get_film_details:
                    # if getting film details, create a TMDB API search using film title and year
                    search = tmdb.Search()
                    resp = search.movie(query=film_title, year=film_year)
                    if "results" in resp:
                        # if we get results from TMDB query, get poster path and runtime
                        film_info = tmdb.Movies(int(resp["results"][0]["id"])).info()
                        film.poster_url = constants.POSTERPATH_URL_BASE + film_info["poster_path"]
                        film.runtime = int(film_info["runtime"])
                # add this film to set
                films.add(film)
            page_number += 1
            if len(list_result) < constants.LIST_PAGE_LENGTH:
                break
        return FilmList(url, films)

    @property
    def film_titles(self) -> List[str]:
        """
        Get list of film titles in this list.

        :return: List of film titles
        """
        return [film.title for film in self.films]

    @staticmethod
    def from_html_string(html: str) -> FilmList:
        """
        Create list from HTML string.

        :param html: HTML string input for a FilmList
        :return: FilmList object
        """
        html_soup = BeautifulSoup(html, "html.parser")
        films: Set[Film] = set()
        list_result = html_soup.find_all("li", class_=constants.FILM_CLASS_NAME)
        for li in list_result:
            films.add(Film(li.a.text, constants.LB_URL_ROOT + li.a["href"]))
        return FilmList("", films)

    def to_dict(self) -> Dict[str, Union[str, List[Dict]]]:
        """
        Create a dictionary representation of this FilmList object.

        :return: dictionary representation of this FilmList object
        """
        return {
            "url": self.url,
            "films": [film.to_dict() for film in self.films],
        }

    def __repr__(self) -> str:
        return f"FilmList(url={self.url},films={self.films})"

    def __len__(self) -> int:
        return len(self.films)

    def __hash__(self) -> int:
        return hash(self.films)

    def __eq__(self, __o: FilmList) -> bool:
        return self.url == __o.url and self.films == __o.films

    def __sub__(self, __o: FilmList) -> List[Film]:
        diff = set([(f.title, f.url) for f in self.films]) - set(
            [(f.title, f.url) for f in __o.films]
        )
        return [Film(f[0], f[1]) for f in diff]


class Member:

    # member's list URL
    contest_url: str

    # member's profile URL
    profile_url: str

    # member's name
    name: str

    # member's list of films
    list: FilmList = FilmList("")

    # number of films watched since last contest update
    _num_films_since_last_update: int = 0

    # films watched since last contest update
    _films_since_last_update: Set[Film] = []

    # member's contest position
    _place: int = -1

    def __init__(
        self,
        name: str,
        contest_url: str,
        profile_url: str,
        list: FilmList = FilmList(""),
    ) -> None:
        self.name = name
        self.contest_url = contest_url
        self.profile_url = profile_url
        self.list = list

    @property
    def place(self) -> int:
        """
        Get member's contest position.

        :return: member's contest position
        """
        return self._place

    @place.setter
    def place(self, value: int) -> None:
        """
        Set member's contest position.

        :param value: new contest position
        """
        self._place = value

    @property
    def num_films_watched(self) -> int:
        """
        Get total number of films watched

        :return: total number of films watched
        """
        return len(self.list)

    @property
    def watchtime(self) -> int:
        """
        Get total watchtime across all films

        :return: total watchtime
        """
        return sum([film.runtime for film in self.list.films])

    @property
    def num_films_since_last_update(self) -> int:
        """
        Get number of films watched since last contest update

        :return: number of films watched since last contest update
        """
        return len(self._films_since_last_update)

    def update_films(self, update: Set[Film]) -> None:
        """
        Update films watched since last update

        :param update: Set of Films in update
        """
        self._films_since_last_update = self.list.films - update

    @property
    def films_watched_since_last_update(self) -> Set[Film]:
        """
        Get Set of Films watched since last contest update.

        :return: Set of Films watched since last contest update
        """
        return self._films_since_last_update

    def to_dict(self) -> Dict[str, Union[str, int, Dict]]:
        """
        Create a dictionary representation of this Member object.

        :return: dictionary representation of this Member object
        """
        return {
            "contest_url": self.contest_url,
            "profile_url": self.profile_url,
            "name": self.name,
            "list": self.list.to_dict(),
            "watchtime": self.watchtime,
            "films_since_last_update": self.num_films_since_last_update,
        }

    def __repr__(self) -> str:
        return f"Member(name={self.name},list={self.list})"

    def __hash__(self) -> int:
        return hash((self.profile_url, self.list))


class Contest:

    # contest name
    name: str

    # List of Members in this contest
    members: List[Member]

    # String containing human-readable contest standings
    standings_string: str = ""

    def __init__(
        self,
        name,
        members: List[Member] = [],
    ) -> None:
        self.name = name
        self.members = members

    @staticmethod
    def from_config(config: dict) -> List[Contest]:
        """
        Create a List of Contests from configuration file dictionary.

        :param config: dictionary containing contents from configuration file
        :return: List of Contests
        """
        contests: List[Contest] = []
        for contest_conf in config:
            members: List[Member] = []
            for member_conf in contest_conf["members"]:
                member = Member(
                    name=member_conf["name"],
                    profile_url=member_conf["profile_url"],
                    contest_url=member_conf["contest_url"],
                    list=FilmList(
                        url=member_conf["contest_url"],
                        films=set(
                            [
                                Film(
                                    title=film["title"],
                                    url=film["url"],
                                    runtime=film["runtime"],
                                    poster_url=film["poster_url"],
                                )
                                for film in member_conf["list"]["films"]
                            ]
                        ),
                    ),
                )
                members.append(member)
            contests.append(
                Contest(
                    name=contest_conf["name"],
                    members=members,
                )
            )
        return contests

    async def update(self, get_film_details: bool = True, save_on_update: bool = True) -> bool:
        """
        Update contest.

        :param get_film_details: if details from TMDB should be retrieved for films
        :save_on_update: if contest should be saved to configuration file/database after update
        :return: `True` if contest has changed since last update, `False` otherwise
        """
        print("Updating...")
        is_changed = False
        # iterate though members in this contest
        for member in self.members:
            # create a copy of the member for comparison
            member_last = copy.deepcopy(member)
            # set member list from their contest url
            member.list = await FilmList.from_url(
                url=member_last.contest_url,
                get_film_details=get_film_details,
            )
            if member.list != member_last.list:
                # if member is different than original, contest is changed
                is_changed = True
                # update films watched since last update
                member.update_films(member_last.list.films)

        # sort members by number of films watched first and watchtime second
        self.members.sort(key=lambda x: (x.num_films_watched, x.watchtime), reverse=True)

        if save_on_update and is_changed:
            self.save()
        else:
            print("No change since last update.")

        self.update_standings()
        return is_changed

    def update_standings(self) -> None:
        """Update string representation of standings and print to log."""
        self.time_last_update = datetime.now()
        self.standings_string = (
            f'Standings as of {self.time_last_update.strftime("%m/%d %H:%M")}:\n'
        )
        place = 1
        for member in self.members:
            member.place = place
            place += 1
            self.standings_string += (
                f"* {map_place(member.place)}\t"
                f"{member.name}:\t"
                f"{member.num_films_watched}\t"
                f"(+{member.num_films_since_last_update})\t"
                f"{member.watchtime / 60:.1f}hrs"
                "\n"
            )
        print(self.standings_string)

    def to_dict(self) -> Dict[str, Union[str, List[Dict]]]:
        """
        Create a dictionary representation of this Contest object.

        :return: dictionary representation of this Contest object
        """
        return {
            "name": self.name,
            "members": [member.to_dict() for member in self.members],
        }

    def load(self) -> None:
        """Load contest from config/database."""
        print(f"Attempting to load from database at '{constants.DB_PATH}'...")
        try:
            with open(constants.DB_PATH, "r") as db_file:
                saved_data = yaml.safe_load(db_file)
                if saved_data is None:
                    return
                conf = Contest.from_config(saved_data["contests"], from_config=False)[0]
                self.members = conf.members
            print("Loaded!")
        except OSError as e:
            print(f"Problem with database file at '{constants.DB_PATH}': ", e)

    def save(self) -> None:
        """Save contest to config/database."""
        print(f"Attempting to save to database at '{constants.DB_PATH}'...")
        try:
            with open(constants.DB_PATH, "w") as db_file:
                db_file.write(
                    yaml.safe_dump(
                        {
                            "contests": [self.to_dict()],
                        }
                    )
                )
            print("Saved!")
        except OSError as e:
            print(f"Problem with database file at '{constants.DB_PATH}': ", e)

    def to_image(self, show_last_update: bool = True, show_watchtime: bool = False) -> List[str]:
        """
        Create image from contest standings.

        :param show_last_update: if full update should be shown instead of just the standings
        :param show_watchtime: if member watchtime should be shown
        """
        # height of created image
        html_height = constants.IMAGE_BASE_HEIGHT
        # html str w/ current scores, num of films watched since last update
        html_members = ""
        # html str w/ all member's films watched since last update
        html_updates = ""
        for member in self.members:
            # html str w/ a member's films watched since last update
            html_films = ""
            # set number of films watched since last update if >0 and if watchtime should be shown
            html_films_since_last_update = (
                f"(+{member.num_films_since_last_update})"
                if member.num_films_since_last_update > 0 and show_last_update
                else ""
            )
            # format member section of standings template to add member
            html_members += constants.HTML_STANDINGS_MEMBER.format(
                place=map_place(member.place),
                name=member.name,
                num_films_watched=member.num_films_watched,
                films_since_last_update=html_films_since_last_update,
                hours_class="hidden" if not show_watchtime else "",
                hours_watched=f"{member.watchtime / 60:.1f}hrs",
            )
            # skip adding member, films to update section if no films in this update
            if member.num_films_since_last_update < 1 or not show_last_update:
                continue
            # add films to update section's films
            for film in member._films_since_last_update:
                # format film update template to add films
                html_films += constants.HTML_STANDINGS_UPDATE_FILMS.format(
                    poster=film.poster_url,
                    rating=film.rating,
                )
            # add this member to update section of standings template
            html_updates += constants.HTML_STANDINGS_UPDATE.format(
                name=member.name, films=html_films
            )
            # add 175px to height of image per member with film update
            html_height += 175
        # format standings template
        html = constants.HTML_STANDINGS_TEMPLATE.format(
            head=constants.HTML_HEAD,
            time=self.time_last_update.strftime("%m/%d %H:%M"),
            members=html_members,
            updates=html_updates,
            updates_head_class="" if show_last_update else "hidden",
            updates_head="Since Last Update" if show_last_update else "",
            updates_class="films" if show_last_update else "hidden",
            title_class="",
            members_class="",
            hr_class="films" if show_last_update else "hidden",
        )
        return html_to_image(
            html=html,
            out="update_image.png",
            size=(480, html_height + 40 if show_last_update else html_height),
        )
