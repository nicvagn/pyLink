"""NicLink driver for ChessNut air"""

#  NicLink is free software: you can redistribute it and/or modify it under
#  the terms of the gnu general public license as published by the free
#  software foundation, either version 3 of the license, or (at your option)
#  any later version.
#
#  NicLink is distributed in the hope that it will be useful, but without any
#  warranty; without even the implied warranty of merchantability or fitness
#  for a particular purpose.
#  see the gnu general public license for more details.
#
#  you should have received a copy of the gnu general public license along with
#  NicLink. if not, see <https://www.gnu.org/licenses/>.

import logging
# system
import sys
import threading
import time

# pip libraries
import chess
import numpy as np
import numpy.typing as npt

# EaskLink pybind interface
from . import _niclink
# mine
from .nl_exceptions import ExitNicLink, IllegalMove, NoMove, NoNicLinkFen

### CONSTANTS ###
ONES = np.array(
    [
        "11111111",
        "11111111",
        "11111111",
        "11111111",
        "11111111",
        "11111111",
        "11111111",
        "11111111",
    ],
    dtype=np.str_,
)
ZEROS = np.array(
    [
        "00000000",
        "00000000",
        "00000000",
        "00000000",
        "00000000",
        "00000000",
        "00000000",
        "00000000",
    ],
    dtype=np.str_,
)

FILES = np.array(["a", "b", "c", "d", "e", "f", "g", "h"])

NO_MOVE_DELAY = 0.03  # I think having a logger delay makes board unresponsive

LIGHT_THREAD_DELAY = 0.2

# get a logger, should have structured the module better
logger = logging.getLogger(__name__)


class NicLinkManager(threading.Thread):
    """manage ChessNut air external board in it's own thread"""

    def __init__(
        self,
        refresh_delay: float,
        logger: logging.Logger | None,
        thread_sleep_delay=1,
        bluetooth: bool = False,
    ):
        """initialize the link to the chessboard, and set up NicLink"""

        # initialize the thread, as a daemon
        threading.Thread.__init__(self, daemon=True)

        # HACK: delay for how long threads should sleep, letting threads work
        self.thread_sleep_delay = thread_sleep_delay

        # ensure we have a logger
        if logger is None:
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = logger

        # if bluetooth:
        #    # connect the board w bluetooth
        #    self.nl_interface = nl_bluetooth
        # else:
        # connect with the external board usb
        self.nl_interface = _niclink

        self.refresh_delay = refresh_delay

        try:
            self.connect()
        except RuntimeError:
            print(
                "Error: Can not connect to the chess board. Is it connected \
and turned on?"
            )
            sys.exit("board connection error.")

        # set NicLink values to defaults
        self.reset()

        # IE:
        # ### Treading Events ###
        # # a way to kill the program from outside
        # self.game_over = threading.Event()
        # self.has_moved = threading.Event()
        # self.kill_switch = threading.Event()
        # self.start_game = threading.Event()

        # # threading lock # #
        # used for access to critical vars to prevent race conditions
        # and such
        self.lock = threading.Lock()

    def start_960(self, starting_fen: str) -> None:
        """Start a chess 960 game

        Parameters
        ----------
        starting_fen : str
            the starting fen the 960 game start's with

        side-effects
        ------------
        end's a game if one is running
        """

        # reset for a new game
        self.reset()

        # but change starting board to be our starting fen
        self.starting_fen = starting_fen
        self.game_board = chess.Board(self.starting_fen)

        self.logger.info("start_960(...): 960 game started. Initial fen: %s", self.starting_fen)

    def run(self) -> None:
        """run and wait for a game to begin
        Raises:
            ExitNicLink: to exit the NicLinkManager thread
        """
        # run while kill_switch is not set
        while not self.kill_switch.is_set():
            if self.start_game.is_set():
                self.logger.info("_run_game is set. (run)")
                self._run_game()
            time.sleep(self.thread_sleep_delay)

        # disconnect from board
        self.disconnect()

        raise ExitNicLink("Thank you for using NicLink (raised in NicLinkManager.run()")

    def _run_game(self) -> None:
        """handle a chess game over NicLink"""
        # run a game, ie wait for GameOver event
        self.game_over.wait()
        # game is over, reset NicLink
        self.reset()
        self.logger.info(
            "\n\n _run_game(...): game_over event set, resetting NicLink\n"
        )

    def connect(self, bluetooth: bool = False) -> None:
        """connect to the chessboard
        @param: bluetooth - should we use bluetooth
        """

        # connect to the chessboard, this must be done first
        self.nl_interface.connect()

        # FIX: give time for NL to connect
        time.sleep(self.thread_sleep_delay)
        test_fen = self.nl_interface.get_fen()
        time.sleep(self.thread_sleep_delay)
        # make sure get_fen is working
        test_fen = self.nl_interface.get_fen()

        if test_fen == "":
            exception_message = "Board initialization error. '' or None \
for fen. Is the board connected and turned on?"

            raise RuntimeError(exception_message)

        self.logger.info("Board initialized. initial fen: |%s|" % test_fen)

    def disconnect(self) -> None:
        """disconnect from the chessboard"""
        self.nl_interface.disconnect()
        self.logger.info("\n-- Board disconnected --\n")

    def beep(self) -> None:
        """make the chessboard beep"""
        self.nl_interface.beep()

    def reset(self) -> None:
        """reset NicLink"""

        # reset starting fen
        self.starting_fen = None
        # this instances game board
        self.game_board = chess.Board()
        # the last move the user has played
        self.last_move = None
        # turn off all the lights
        self.turn_off_all_leds()

        # ## Treading Events ###
        # a way to kill the program from outside
        self.game_over = threading.Event()
        self.has_moved = threading.Event()
        self.kill_switch = threading.Event()
        self.start_game = threading.Event()

        self.logger.debug("NicLinkManager reset\n")

    def set_led(self, square: str, status: bool) -> None:
        """set an led at a given square to a status
        @param: square (square: a1, e4 etc)
        @param: status: True | False
        @side_effect: changes led on chessboard
        """

        # find the file number by iteration
        found = False
        letter = square[0]

        file_num = 0
        while file_num < 8:
            if letter == FILES[file_num]:
                found = True
                break
            file_num += 1

        # find the number by straight conversion, and some math.
        num = int(square[1]) - 1  # it's 0 based

        if not found:
            raise ValueError(f"{square[1]} is not a valid file")

        # this is supper fd, but the chessboard internally starts counting at h8
        self.nl_interface.set_led(7 - num, 7 - file_num, status)

    def set_move_leds(self, move: str) -> None:
        """highlight a move. Light up the origin and destination led
        @param: move: a move in uci
        @side_effect: changes board led's. Shut's off all led's,
        and display's  the move
        """
        self.logger.info("man.set_move_leds( %s ) called\n", move)

        move_led_map = build_led_map_for_move(move)
        # log led map
        self.logger.debug("move led map created. Move: %s \n map: ", move)
        log_led_map(move_led_map, self.logger)

        self.set_all_leds(move_led_map)

    def set_all_leds(self, light_board: npt.NDArray[np.str_]) -> None:
        """set all led's on ext. chess board
        @param: light_board - a list of len 8 made up of
                str of len 8 with the 1 for 0 off
                for the led of that square
        """
        self.logger.debug(
            "set_all_leds(light_board: np.ndarray[np.str_]):  \
called with following light_board:"
        )

        log_led_map(light_board, self.logger)

        # the pybind11 use 8 str, because it is difficult
        # to use complex data structures between languages
        self.nl_interface.set_all_leds(
            str(light_board[0]),
            str(light_board[1]),
            str(light_board[2]),
            str(light_board[3]),
            str(light_board[4]),
            str(light_board[5]),
            str(light_board[6]),
            str(light_board[7]),
        )

    def turn_off_all_leds(self) -> None:
        """turn off all the leds"""
        self.nl_interface.lights_out()

    def signal_lights(self, sig_num: int) -> None:
        """signal the user via displaying a set of lights on the board
        @param: sig_num - the signal number corresponding to the signal to show
                ie: 1 - ring of lights
                    2 - black half lit up
                    3 - white half lit up
                    4 - central line
                    5 - cross in center
                    6 - random stuff
        @side effect - change the light's on the chess board
        """
        if sig_num == 1:
            # signal 1 - ring of lights

            sig = np.array(
                [
                    "11111111",
                    "10000001",
                    "10111101",
                    "10100101",
                    "10100101",
                    "10111101",
                    "10000001",
                    "11111111",
                ],
                dtype=np.str_,
            )
            self.set_all_leds(sig)
        elif sig_num == 2:
            # signal 2 - black half lit up
            sig = np.array(
                [
                    "00000000",
                    "00000000",
                    "00000000",
                    "00000000",
                    "11111111",
                    "11111111",
                    "11111111",
                    "11111111",
                ],
                dtype=np.str_,
            )

            self.set_all_leds(sig)
        elif sig_num == 3:
            # signal 3 - white half lit up
            sig = np.array(
                [
                    "11111111",
                    "11111111",
                    "11111111",
                    "11111111",
                    "00000000",
                    "00000000",
                    "00000000",
                    "00000000",
                ],
                dtype=np.str_,
            )
            self.set_all_leds(sig)
        elif sig_num == 4:
            # Signal 4 - center line
            sig = np.array(
                [
                    "11111111",
                    "00000000",
                    "00000000",
                    "11111111",
                    "11111111",
                    "00000000",
                    "00000000",
                    "11111111",
                ],
                dtype=np.str_,
            )
            self.set_all_leds(sig)
        elif sig_num == 5:
            # Signal 5 - center cross
            sig = np.array(
                [
                    "00011000",
                    "01011010",
                    "00011000",
                    "11111111",
                    "11111111",
                    "00011000",
                    "01011010",
                    "00011000",
                ],
                dtype=np.str_,
            )
            self.set_all_leds(sig)
        elif sig_num == 6:
            # Signal 6 - crazy lights
            sig = np.array(
                [
                    "11000011",
                    "11011011",
                    "00011000",
                    "01100110",
                    "01100110",
                    "00011000",
                    "11011011",
                    "11000011",
                ],
                dtype=np.str_,
            )
            self.set_all_leds(sig)

        if self.last_move is not None:
            time.sleep(LIGHT_THREAD_DELAY)
            self.set_move_leds(self.last_move)

    def get_fen(self) -> str:
        """get the board fen from chessboard"""

        fen = self.nl_interface.get_fen()
        if fen is not None:
            return fen
        # else:

        raise NoNicLinkFen("No fen got from board")

    def put_board_fen_on_board(self, board_fen: str) -> chess.Board:
        """show just the board part of fen on asci chessboard,
           then return it for logging purposes
        @param: board_fen: just the board part of a fen,
                          ie: 8/8/8/8/8/8/8 for empty board ...
        @return: a chess.Board with that board fen on it
        """
        tmp_board = chess.Board()
        tmp_board.set_board_fen(board_fen)
        print(tmp_board)
        return tmp_board

    def find_move_from_fen_change(
        self, new_fen: str
    ) -> str:  # a move in coordinate notation
        """get the move that occurred to change the game_board fen
        into a given fen.
        @param: new_fen a board fen of the pos. of external board
        to parse move from
        return: the move in coordinate notation
        """
        old_fen = self.game_board.board_fen()
        if new_fen == old_fen:
            self.logger.debug("no fen difference. fen was %s", old_fen)
            raise NoMove("No fen difference")

        self.logger.debug("new_fen %s", new_fen)
        self.logger.debug("old fen %s", old_fen)

        # get a list of the legal moves
        legal_moves = list(self.game_board.legal_moves)

        tmp_board = self.game_board.copy()
        self.logger.debug(
            "+++ find_move_from_fen_change(...) called +++\n\
current board: \n%s\n board we are using to check legal moves: \n%s\n",
            self.put_board_fen_on_board(self.get_fen()),
            self.game_board,
        )
        # find move by brute force
        for move in legal_moves:
            # self.logger.info(move)
            tmp_board.push(move)  # Make the move on the board

            # Check if the board's fen matches the new fen
            if tmp_board.board_fen() == new_fen:
                self.logger.info("move was found to be: %s", move)

                return move.uci()  # Return the last move

            tmp_board.pop()  # Undo the move and try another

        error_board = chess.Board()
        error_board.set_board_fen(new_fen)
        self.show_board_diff(error_board, self.game_board)
        message = f"Board we see:\n{str(error_board)}\nis not a possible  \
result from a legal move on:\n{str(self.game_board)}\n"

        raise IllegalMove(message)

    def check_game_board_against_external(self) -> bool:
        """check if the external board is a given board fen
        @param fen: str: the fen the ext board should be
        @returns: if the external board fen is == the fen
        """
        nl_fen = self.nl_interface.get_fen()

        return self.game_board.board_fen() == nl_fen

    def check_for_move(self) -> bool | str:
        """check if there has been a move on the chessboard, and see if
        is is valid. If so update self.last_move
        @returns: self.last_move - the move got from the chessboard
        """
        # ensure the move was valid

        # get current fen on the external board
        new_fen = self.nl_interface.get_fen()

        if new_fen is None:
            raise ValueError("No fen from chessboard")
        try:
            # will cause an index error if game_board has no moves
            last_move = self.game_board.pop()

            # check if you just have not moved the opponent's piece
            if new_fen == self.game_board.board_fen():
                self.logger.debug(
                    "board fen is the board fen before opponent move made on  \
                    chessboard. Returning"
                )
                self.game_board.push(last_move)
                time.sleep(self.refresh_delay)
                return False

            self.game_board.push(last_move)
        except IndexError:
            last_move = False  # if it is an empty list of moves

        if new_fen != self.game_board.board_fen:
            # a change has occurred on the chessboard
            # check to see if the game is over
            if self.game_over.is_set():
                return False

            # check if the move is valid, and set last move
            try:
                self.last_move = self.find_move_from_fen_change(new_fen)
            except IllegalMove as err:
                log_handled_exception(err)
                self.logger.warning(
                    "\n===== move not valid, undue it and try again.  \
it is white's turn? %s =====\n board we are using to check for moves:\n%s\n",
                    self.game_board.turn,
                    self.game_board,
                )
                # show the board diff from what we are checking for legal moves
                self.logger.info("diff from board we are checking legal moves on:\n")
                current_board = chess.Board(new_fen)
                self.show_board_diff(current_board, self.game_board)
                # pause for the refresh_delay and allow other threads to run

                time.sleep(self.refresh_delay)
                return False

            # return the move
            with self.lock:
                return self.last_move

        else:
            self.logger.debug("no change in fen.")
            self.turn_off_all_leds()
            # pause for a refresher
            time.sleep(self.refresh_delay)

            return False

    def await_move(self) -> str | None:
        """wait for legal move, and return it in coordinate notation after
        making it on internal board
        """
        # loop until we get a valid move
        attempts = 0
        while not self.kill_switch.is_set():
            self.logger.debug(
                "is game_over threading event set? %s", self.game_over.is_set()
            )
            # check for a move. If it move, return it else False
            try:
                move = False

                # check if the game is over
                if self.game_over.is_set():
                    return None
                if self.check_for_move():
                    move = self.get_last_move()
                if move:  # if we got a move, return it and exit
                    self.logger.info(
                        "move %s made on external board. there where %s  \
                        attempts to get",
                        move,
                        attempts,
                    )
                    return move
                # else
                self.logger.debug("no move")
                # if move is false continue
                continue

            except NoMove:
                # no move made, wait refresh_delay and continue
                attempts += 1
                self.logger.debug("NoMove from chessboard. Attempt: %s", attempts)
                time.sleep(NO_MOVE_DELAY)

                continue

            except IllegalMove as err:
                # IllegalMove made, waiting then trying again
                attempts += 1
                self.logger.error(
                    "\nIllegal Move: %s | waiting NO_MOVE_DELAY= %s and"
                    + " checking again.\n",
                    err,
                    NO_MOVE_DELAY,
                )
                time.sleep(NO_MOVE_DELAY)
                continue

        # exit Niclink
        raise ExitNicLink(
            f"in await_move():\nkill_switch.is_set: {self.kill_switch.is_set()}"
        )

    def get_last_move(self) -> str:
        """get the last move played on the chessboard"""
        with self.lock:
            if self.last_move is None:
                raise ValueError("ERROR: last move is None")

            return self.last_move

    def make_move_game_board(self, move: str) -> None:
        """make a move on the internal rep. of the game_board.
        do not update the last move made, or the move led's on ext board.
        This is not done automatically so external program's
        can have more control.
        @param: move - move in uci str
        """
        self.logger.info("move made on game board. move %s", move)
        self.game_board.push_uci(move)
        self.logger.debug(
            "made move on internal  nl game board, BOARD POST MOVE:\n%s",
            self.game_board,
        )

    def set_board_fen(self, board: chess.Board, fen: str) -> None:
        """set a board up according to a fen"""
        chess.Board.set_board_fen(board, fen=fen)

    def set_game_board_fen(self, fen: str) -> None:
        """set the internal game board fen"""
        self.set_board_fen(self.game_board, fen)

    def show_fen_on_board(self, fen: str) -> chess.Board:
        """print a fen on on a chessboard
        @param: fen - (str) fen to display on board
        @returns: a board with the fen on it
        """
        board = chess.Board()
        self.set_board_fen(board, fen)
        print(board)
        return board  # for logging purposes

    def show_board_state(self) -> None:
        """show the state of the real world board"""
        curfen = self.get_fen()
        self.show_fen_on_board(curfen)

    def show_game_board(self) -> None:
        """print the internal game_board. Return it for logging purposes"""
        print(self.game_board)

    def set_game_board(self, board: chess.Board) -> None:
        """set the game board
        @param: board - the board to set as the game board
        """
        with self.lock:
            self.game_board = board

    def gameover_lights(self) -> None:
        """show some fireworks"""
        self.nl_interface.gameover_lights()

    def square_in_last_move(self, square: str) -> bool:
        """is the square in the last move?
        @param: square - a square in algebraic notation
        @returns: bool - if the last move contains that square
        """
        if self.last_move:
            if square in self.last_move:
                return True

        return False

    def show_board_diff(self, board1: chess.Board, board2: chess.Board) -> bool:
        """show the difference between two boards and output difference on
        the chessboard
        @param: board1 - reference board
        @param: board2 - board to display diff from reference board
        @side_effect: changes led's to show diff squares
        @returns: bool - if there is a diff
        """
        self.logger.debug(
            "man.show_board_diff entered w board's \n%s\nand\n%s",
            board1,
            board2,
        )

        # go through the squares and turn on the light for ones pieces are
        # misplaced
        diff = False
        # for building the diff array that work's for the way we set led's
        zeros = "00000000"
        diff_squares = []  # what squares are the diff's on

        diff_map = np.copy(ZEROS)

        for n in range(0, 8):
            # handle diff's for a file
            for a in range(ord("a"), ord("h")):
                # get the square in algebraic notation form
                square = chr(a) + str(n + 1)  # real life is not 0 based
                py_square = chess.parse_square(square)
                if board1.piece_at(py_square) != board2.piece_at(py_square):
                    # record the diff in diff array, while
                    # keeping the last move lit up
                    if not self.square_in_last_move(square):
                        diff = True
                        self.logger.info(
                            """man.show_board_diff(...): Diff found at \
                            square %s""",
                            square,
                        )

                    # add square to list off diff squares
                    diff_cords = square_cords(square)
                    diff_squares.append(square)

                    diff_map[diff_cords[1]] = (
                        zeros[: diff_cords[0]] + "1" + zeros[diff_cords[0] :]
                    )

        if diff:
            # set all the led's that differ
            self.set_all_leds(diff_map)
            self.logger.warning(
                "show_board_diff: diff found --> diff_squares: %s\n",
                diff_squares,
            )

            self.logger.debug(
                "diff boards:\nInternal Board:\n%s\nExternal board:\n%s\n",
                str(board1),
                str(board2),
            )
            self.logger.debug("diff map made:")
            log_led_map(diff_map, self.logger)

            print(f"diff from game board --> diff_squares: {diff_squares}\n")

        else:
            if self.last_move is not None:
                # set the last move lights for last move
                self.set_move_leds(self.last_move)

        return diff

    def get_game_fen(self) -> str:
        """get the game board fen"""
        return self.game_board.fen()

    def is_game_over(
        self,
    ) -> dict | bool:
        """is the internal game over?"""
        if self.game_board.is_checkmate():
            return {
                "over": True,
                "winner": self.game_board.turn,
                "reason": "checkmate",
            }
        if self.game_board.is_stalemate():
            return {"over": True, "winner": False, "reason": "Is a stalemate"}
        if self.game_board.is_insufficient_material():
            return {
                "over": True,
                "winner": False,
                "reason": "Is insufficient material",
            }
        if self.game_board.is_fivefold_repetition():
            return {
                "over": True,
                "winner": False,
                "reason": "Is fivefold repetition.",
            }
        if self.game_board.is_seventyfive_moves():
            return {
                "over": True,
                "winner": False,
                "reason": "A game is automatically drawn if the half-move clock"
                + " since a capture or pawn move is equal to or greater"
                + " than 150. Other means to end a game take precedence.",
            }

        return False

    def opponent_moved(self, move: str) -> None:
        """the other player moved in a chess game.
        Signal ledS_changed and update last move
        @param: move - the move in a uci str
        @side_effect: set's move led's
        """
        self.logger.debug("opponent moved %s", move)
        self.last_move = move
        self.set_move_leds(move)


# === helper functions ===
def square_cords(square) -> tuple[int, int]:
    """find coordinates for a given square on the chess board. (0, 0)
    is a1.
    @params: square - std algebraic square, ie b3, a8
    @returns: tuple of the (x, y) coord of the square (0 based) (file, rank)
    """
    rank = int(square[1]) - 1  # it's 0 based

    # find the file number by iteration
    found = False
    letter = square[0]
    file_num = 0
    while file_num < 8:
        if letter == FILES[file_num]:
            found = True
            break
        file_num += 1

    if not found:
        raise ValueError(f"{square[0]} is not a valid file")

    return (file_num, rank)


def log_led_map(led_map: npt.NDArray[np.str_], loggr) -> None:
    """log led map pretty 8th file to the top"""
    loggr.debug("\nLOG LED map:\n")
    loggr.debug(str(led_map[7]))
    loggr.debug(str(led_map[6]))
    loggr.debug(str(led_map[5]))
    loggr.debug(str(led_map[4]))
    loggr.debug(str(led_map[3]))
    loggr.debug(str(led_map[2]))
    loggr.debug(str(led_map[1]))
    loggr.debug(str(led_map[0]))


def build_led_map_for_move(move: str) -> npt.NDArray[np.str_]:
    """build the led_map for a given uci move
    @param: move - move in uci
    @return: constructed led_map
    """
    zeros = "00000000"
    logger.debug("build_led_map_for_move(%s)", move)

    led_map = np.copy(ZEROS)

    # get the square cords and the coordinates
    s1 = move[:2]
    s2 = move[2:]
    s1_cords = square_cords(s1)
    s2_cords = square_cords(s2)

    # if they are not on the same rank
    if s1_cords[1] != s2_cords[1]:
        # set 1st square
        led_map[s1_cords[1]] = zeros[: s1_cords[0]] + "1" + zeros[s1_cords[0] :]
        logger.debug("map after 1st move cord (cord): %s", s1_cords)
        log_led_map(led_map, logger)
        # set second square
        led_map[s2_cords[1]] = zeros[: s2_cords[0]] + "1" + zeros[s2_cords[0] :]
        logger.debug("led map made for move: %s\n", move)
        log_led_map(led_map, logger)
    # if they are on the same rank
    else:
        rank = list(zeros)
        rank[s1_cords[0]] = "1"
        rank[s2_cords[0]] = "1"

        logger.debug("led rank computed: %s", rank)

        rank_str = "".join(rank)

        # insert into led_map as numpy string
        led_map[s1_cords[1]] = np.str_(rank_str)

    return led_map


# ==== logger setup ====
def set_up_logger() -> None:
    """Only run when this module is run as __main__"""

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(module)s %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.ERROR)
    logger.addHandler(console_handler)

    # logging to a file
    file_handler = logging.FileHandler("NicLink.log")
    logger.addHandler(file_handler)

    debug = False
    if debug:
        logger.info("DEBUG is set.")
        logger.setLevel(logging.DEBUG)
        file_handler.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
    else:
        logger.info("DEBUG not set")
        file_handler.setLevel(logging.INFO)
        logger.setLevel(logging.ERROR)
        console_handler.setLevel(logging.ERROR)


#  === exception logging ===
# log unhandled exceptions to the log file
def log_except_hook(exc_type, exc_value, traceback):
    """catch all the thrown exceptions for logging"""
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, traceback))


def log_handled_exception(exception: Exception) -> None:
    """log a handled exception"""
    logger.debug("Exception handled: %s", exception)


# setup except hook
sys.excepthook = log_except_hook
