#
#  NicLink is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
#
#  NicLink is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along with NicLink. If not, see <https://www.gnu.org/licenses/>.

# a basic test of NicLink through python interface

import test

import readchar
import tests

import niclink


def tests() -> None:
    """Run the tests"""
    print("runing tests.")


print("create NicLinkManager? (y,n)")
t = readchar.readchar()


if t != n:
    nl = niclink.NicLinkManager(2)
    tests.__main__()


def test() -> None:
    """test"""

    print("press enter when a move is on a board")
    readchar.readkey()

    leave = "n"
    while leave == "n":
        if nl.check_for_move():
            # beep to indicate a move was made
            nl.beep()

            # get the new board FEN
            post_move_FEN = nl.get_FEN()

            try:
                # find move from the FEN change
                move = nl.get_last_move()
            except RuntimeError as re:
                print(
                    f" Invalid move: {re} \nreset the board to the previous position an try again\n"
                )
                print(f"previous position: \n{nl.game_board}\n")
                print("leave? ('n' for no, != 'n' yes: ")
                leave = readchar.readkey()

                continue  # as move will not be defined

            # make the move on the game board
            nl.make_move_game_board(move)
            print(f"MOVE: {move}")
            print("=========================================")

        print("leave? ('n for no, != 'n' yes: ")
        leave = readchar.readkey()


if __name__ == "__main__":
    test()
