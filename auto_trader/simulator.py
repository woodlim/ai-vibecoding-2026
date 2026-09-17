def print_multiplication_table(dan: int) -> None:
    """입력받은 단의 구구단을 출력한다."""
    print(f"\n[{dan}단]")
    for number in range(1, 10):
        print(f"{dan} x {number} = {dan * number}")


def print_all_tables() -> None:
    """2단부터 9단까지의 구구단을 모두 출력한다."""
    for dan in range(2, 10):
        print_multiplication_table(dan)


def main() -> None:
    user_input = input(
        "출력할 단을 입력하세요 (2~9, 전체 출력은 Enter 또는 '전체'): "
    ).strip()

    if user_input == "" or user_input == "전체":
        print_all_tables()
        return

    try:
        dan = int(user_input)
    except ValueError:
        print("숫자 2~9 또는 '전체'를 입력해 주세요.")
        return

    if 2 <= dan <= 9:
        print_multiplication_table(dan)
    else:
        print("2부터 9 사이의 숫자를 입력해 주세요.")


if __name__ == "__main__":
    main()
